"""Run an MCP server that exposes this project's DRF APIs as LLM tools.

Runs in-process with Django (no HTTP hop): every tool drives the real
ViewSet classes registered on `tasks.urls.router`, so permissions,
serializers, filtering, and validation all execute exactly as they do for a
normal HTTP request. To expose another app's API, add its router to
ROUTERS below -- no new tool code needed.

Usage:
    python manage.py mcp_serve
"""

from django.core.management.base import BaseCommand
from mcp.server.fastmcp import FastMCP

from config.mcp_tools import register_viewset_tools
from tasks.urls import router as tasks_router

ROUTERS = [tasks_router]


class Command(BaseCommand):
    help = "Run the MCP (stdio) server that exposes DRF ViewSets as LLM tools."

    def handle(self, *args, **options):
        mcp = FastMCP("django-tasks")
        for router in ROUTERS:
            register_viewset_tools(mcp, router)
        mcp.run()
