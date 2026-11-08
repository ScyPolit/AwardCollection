from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from . import tests as fixtures
from .models import Template, TemplateVersion
from .permissions import grant_owner
from .prepared import allowed
from .serializers import BatchSerializer
from types import SimpleNamespace


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class TemplateAccessTests(TestCase):
    setUp = fixtures.WorkflowTests.setUp

    def client_as(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def copy(self):
        source = self.version.template_version.template
        response = self.client_as(self.owner).post(f"/api/v1/templates/{source.pk}/copy/", {"department": source.department_id, "name": "我的模板"}, format="json")
        self.assertEqual(response.status_code, 201)
        return Template.objects.get(pk=response.data["id"])

    def test_personal_copy_is_private_and_not_department_managed(self):
        copy = self.copy()
        self.assertEqual(copy.scope, "personal")
        self.assertFalse(copy.published)
        grant_owner(self.outsider)
        for user in (self.outsider, self.admin_a, self.admin_b):
            client = self.client_as(user)
            self.assertNotIn(copy.pk, [x["id"] for x in client.get("/api/v1/templates/").data])
            self.assertEqual(client.get(f"/api/v1/templates/{copy.pk}/").status_code, 404)
            self.assertEqual(client.post(f"/api/v1/templates/{copy.pk}/copy/", {"department": copy.department_id}, format="json").status_code, 404)
            self.assertFalse(allowed(user, SimpleNamespace(version_id=None, template_version_id=copy.versions.get().pk)))
        self.assertTrue(self.client_as(self.owner).get(f"/api/v1/templates/{copy.pk}/").data["can_edit"])
        self.assertTrue(self.client_as(self.superuser).get(f"/api/v1/templates/{copy.pk}/").data["can_manage"])

    def test_owner_can_edit_share_and_unshare_only_own_copy(self):
        copy = self.copy()
        owner = self.client_as(self.owner)
        saved = owner.post(f"/api/v1/templates/{copy.pk}/save_version/", {"expected_version": 1, "canvas": {"title": "个人证书"}}, format="json")
        self.assertEqual(saved.status_code, 201)
        self.assertEqual(owner.patch(f"/api/v1/templates/{copy.pk}/", {"published": True}, format="json").status_code, 200)
        other = self.client_as(self.admin_b)
        self.assertEqual(other.get(f"/api/v1/templates/{copy.pk}/").status_code, 200)
        self.assertEqual(other.post(f"/api/v1/templates/{copy.pk}/save_version/", {"canvas": {}}, format="json").status_code, 403)
        self.assertEqual(other.patch(f"/api/v1/templates/{copy.pk}/", {"published": False}, format="json").status_code, 403)
        self.assertEqual(other.delete(f"/api/v1/templates/{copy.pk}/").status_code, 403)
        owner.patch(f"/api/v1/templates/{copy.pk}/", {"published": False}, format="json")
        self.assertEqual(other.get(f"/api/v1/templates/{copy.pk}/").status_code, 404)
        self.assertEqual(self.version.template_version.template.versions.count(), 1)

    def test_private_templates_are_usable_only_by_authorized_users(self):
        copy = self.copy()
        version = copy.versions.get()
        for user, expected in ((self.owner, True), (self.admin_a, False), (self.superuser, True)):
            serializer = BatchSerializer(data={"name": "私有模板批次", "competition": self.batch.competition_id, "template_version": version.pk}, context={"request": SimpleNamespace(user=user)})
            self.assertEqual(serializer.is_valid(), expected, serializer.errors)

    def test_owner_cannot_change_template_scope_to_bypass_ownership(self):
        copy = self.copy()
        self.client_as(self.owner).patch(f"/api/v1/templates/{copy.pk}/", {"scope": "department", "department": self.departments[1].pk}, format="json")
        copy.refresh_from_db()
        self.assertEqual(copy.scope, "personal")
        self.assertEqual(copy.department_id, self.departments[0].pk)
