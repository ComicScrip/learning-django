from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from .models import Task
from .serializers import TaskSerializer

User = get_user_model()


class TaskModelTests(TestCase):
    def test_str_returns_title(self):
        task = Task.objects.create(title='Write tests')
        self.assertEqual(str(task), 'Write tests')

    def test_completed_defaults_to_false(self):
        task = Task.objects.create(title='Write tests')
        self.assertFalse(task.completed)

    def test_ordering_is_newest_first(self):
        older = Task.objects.create(title='Older')
        newer = Task.objects.create(title='Newer')
        self.assertEqual(list(Task.objects.all()), [newer, older])


class TaskSerializerTests(TestCase):
    def test_read_only_fields_are_not_writable(self):
        task = Task.objects.create(title='Existing')
        serializer = TaskSerializer(
            task,
            data={'id': 999, 'title': 'Changed', 'created_at': '2000-01-01T00:00:00Z'},
            partial=True,
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.id, task.id)
        self.assertEqual(updated.title, 'Changed')


class TaskAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='alice', password='s3cret-pass')
        self.task = Task.objects.create(title='Existing task', description='desc')

    def test_anonymous_can_list_tasks(self):
        response = self.client.get(reverse('task-list'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)

    def test_anonymous_cannot_create_task(self):
        response = self.client.post(reverse('task-list'), {'title': 'New task'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Task.objects.count(), 1)

    def test_authenticated_user_can_create_task(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('task-list'), {'title': 'New task'})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Task.objects.count(), 2)

    def test_authenticated_user_can_update_task(self):
        self.client.force_login(self.user)
        url = reverse('task-detail', args=[self.task.id])
        response = self.client.patch(url, {'completed': True})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.task.refresh_from_db()
        self.assertTrue(self.task.completed)

    def test_authenticated_user_can_delete_task(self):
        self.client.force_login(self.user)
        url = reverse('task-detail', args=[self.task.id])
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Task.objects.count(), 0)

    def test_filter_by_completed(self):
        Task.objects.create(title='Done task', completed=True)
        response = self.client.get(reverse('task-list'), {'completed': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['title'], 'Done task')

    def test_search_by_title(self):
        Task.objects.create(title='Buy milk')
        response = self.client.get(reverse('task-list'), {'search': 'milk'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['title'], 'Buy milk')
