"""Generic bridge from DRF ViewSets to MCP tools.

The goal is "single source of truth": tool handlers don't reimplement
permissions, serialization, filtering, or validation. Instead each tool
drives the *real* DRF ViewSet class in-process via
`rest_framework.test.APIRequestFactory` -- the same code path Django uses to
serve an actual HTTP request, minus the network hop. If a ViewSet's
permissions, serializer fields, or business logic change, every MCP tool
built from it picks up the change automatically; nothing here needs editing.

Usage (see tasks/management/commands/mcp_serve.py):

    from mcp.server.fastmcp import FastMCP
    from config.mcp_tools import register_viewset_tools
    from tasks.urls import router as tasks_router

    mcp = FastMCP("django-tasks")
    register_viewset_tools(mcp, tasks_router)
    mcp.run()
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import sync_to_async
from rest_framework.response import Response
from rest_framework.routers import BaseRouter
from rest_framework.test import APIRequestFactory

_factory = APIRequestFactory()


def _call_view(
    viewset_cls: type,
    action: str,
    method: str,
    *,
    path: str,
    data: dict[str, Any] | None = None,
    query: dict[str, Any] | None = None,
    pk: str | None = None,
) -> Response:
    """Dispatch a single DRF viewset action in-process.

    Builds a request the same way DRF's own test utilities do, then routes
    it through `viewset_cls.as_view(...)` exactly as the real router would --
    so permission checks, serializer validation, and filter backends all run
    unmodified.
    """
    method = method.upper()
    if method == "GET":
        django_request = _factory.get(path, query or {})
    elif method == "POST":
        django_request = _factory.post(path, data or {}, format="json")
    elif method == "PUT":
        django_request = _factory.put(path, data or {}, format="json")
    elif method == "PATCH":
        django_request = _factory.patch(path, data or {}, format="json")
    elif method == "DELETE":
        django_request = _factory.delete(path)
    else:
        raise ValueError(f"Unsupported HTTP method: {method}")

    view = viewset_cls.as_view({method.lower(): action})
    kwargs = {"pk": pk} if pk is not None else {}
    return view(django_request, **kwargs)


# Django's ORM refuses synchronous DB access from a thread with a running
# event loop (SynchronousOnlyOperation). MCP tool handlers are async, so
# every view dispatch must hop onto a worker thread via sync_to_async.
_call_view_async = sync_to_async(_call_view, thread_sensitive=True)


def register_viewset_tools(mcp: Any, router: BaseRouter) -> None:
    """Register MCP tools for every ViewSet in a DRF router.

    For each registered (prefix, viewset, basename), generates whichever of
    list/retrieve/create/update/delete tools the ViewSet actually supports
    (checked via hasattr, so a ReadOnlyModelViewSet only gets read tools).
    """
    for prefix, viewset_cls, basename in router.registry:
        _register_one(mcp, prefix, viewset_cls, basename)


def _register_one(mcp: Any, prefix: str, viewset_cls: type, basename: str) -> None:
    path = f"/{prefix}/"

    if hasattr(viewset_cls, "list"):

        async def list_tool(
            filters: dict[str, str] | None = None,
            search: str | None = None,
            page: int | None = None,
        ) -> dict[str, Any]:
            query: dict[str, Any] = dict(filters or {})
            if search:
                query["search"] = search
            if page is not None:
                query["page"] = page
            response = await _call_view_async(viewset_cls, "list", "GET", path=path, query=query)
            return response.data

        list_tool.__name__ = f"list_{basename}"
        list_tool.__doc__ = (
            f"List {basename} objects (mirrors GET {path}). "
            f"`filters` maps query params (e.g. filterset fields) to values; "
            f"`search` matches the ViewSet's search_fields; results are paginated, "
            f"pass `page` for subsequent pages."
        )
        mcp.tool()(list_tool)

    if hasattr(viewset_cls, "retrieve"):

        async def get_tool(id: str) -> dict[str, Any]:
            response = await _call_view_async(viewset_cls, "retrieve", "GET", path=f"{path}{id}/", pk=id)
            if response.status_code >= 400:
                raise ValueError(response.data)
            return response.data

        get_tool.__name__ = f"get_{basename}"
        get_tool.__doc__ = f"Retrieve a single {basename} by id (mirrors GET {path}{{id}}/)."
        mcp.tool()(get_tool)

    if hasattr(viewset_cls, "create"):

        async def create_tool(data: dict[str, Any]) -> dict[str, Any]:
            response = await _call_view_async(viewset_cls, "create", "POST", path=path, data=data)
            if response.status_code >= 400:
                raise ValueError(response.data)
            return response.data

        create_tool.__name__ = f"create_{basename}"
        create_tool.__doc__ = f"Create a new {basename} (mirrors POST {path})."
        mcp.tool()(create_tool)

    if hasattr(viewset_cls, "partial_update"):

        async def update_tool(id: str, data: dict[str, Any]) -> dict[str, Any]:
            response = await _call_view_async(
                viewset_cls, "partial_update", "PATCH", path=f"{path}{id}/", data=data, pk=id
            )
            if response.status_code >= 400:
                raise ValueError(response.data)
            return response.data

        update_tool.__name__ = f"update_{basename}"
        update_tool.__doc__ = (
            f"Partially update a {basename} by id (mirrors PATCH {path}{{id}}/). "
            f"`data` only needs the fields being changed."
        )
        mcp.tool()(update_tool)

    if hasattr(viewset_cls, "destroy"):

        async def delete_tool(id: str) -> dict[str, Any]:
            response = await _call_view_async(viewset_cls, "destroy", "DELETE", path=f"{path}{id}/", pk=id)
            if response.status_code >= 400:
                raise ValueError(response.data)
            return {"deleted": True, "id": id}

        delete_tool.__name__ = f"delete_{basename}"
        delete_tool.__doc__ = f"Delete a {basename} by id (mirrors DELETE {path}{{id}}/)."
        mcp.tool()(delete_tool)
