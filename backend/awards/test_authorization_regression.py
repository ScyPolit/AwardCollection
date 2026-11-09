"""API regressions for the November 2026 gray-box authorization review."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import tests as fixtures
from .models import (
    AccountProfile, AuditEvent, AwardBatch, Certificate, Competition, DepartmentMembership,
    GenerationTask,
)
from .permissions import OWNER_GROUP, grant_owner, is_owner


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuthorizationRegressionTests(TestCase):
    def setUp(self):
        fixtures.WorkflowTests.setUp(self)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.own_account = get_user_model().objects.create_user("created_here")
        AccountProfile.objects.create(user=self.own_account, created_by=self.admin_a)
        self.foreign_owner = get_user_model().objects.create_user("foreign_owner")
        grant_owner(self.foreign_owner)
        AccountProfile.objects.create(user=self.foreign_owner, created_by=self.admin_b)

    def competition_payload(self, **extra):
        return {"name": "权限复测竞赛", "departments": [self.departments[0].pk], **extra}

    def test_account_creation_rejects_department_injection_without_any_writes(self):
        self.client.force_authenticate(self.admin_a)
        for extra in (
            {"department_id": self.departments[1].pk},
            {"department": self.departments[1].pk},
            {"is_superuser": True},
            {"is_staff": True},
            {"role": "super"},
        ):
            with self.subTest(extra=extra):
                response = self.client.post("/api/v1/management/accounts/", {
                    "username": "injected_account", "password": "Regression-Strong-2026!",
                    "role": "owner", **extra,
                }, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertFalse(get_user_model().objects.filter(username="injected_account").exists())
        self.assertFalse(AuditEvent.objects.filter(action="account.created").exists())

    def test_department_admin_cannot_create_foreign_department_admin(self):
        self.client.force_authenticate(self.admin_a)
        response = self.client.post("/api/v1/management/accounts/", {
            "username": "injected_admin", "password": "Regression-Strong-2026!",
            "role": "admin", "department": self.departments[1].pk,
        }, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(get_user_model().objects.filter(username="injected_admin").exists())

    def test_superuser_can_create_admin_only_for_live_department(self):
        self.client.force_authenticate(self.superuser)
        self.departments[1].deleted_at = timezone.now()
        self.departments[1].save()
        payload = {"username": "new_admin", "password": "Regression-Strong-2026!", "role": "admin"}
        response = self.client.post("/api/v1/management/accounts/", {
            **payload, "department": self.departments[1].pk,
        }, format="json")
        self.assertEqual(response.status_code, 400, response.data)
        response = self.client.post("/api/v1/management/accounts/", {
            **payload, "department": self.departments[0].pk,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(DepartmentMembership.objects.filter(
            user_id=response.data["id"], department=self.departments[0], role="admin",
        ).exists())

    def test_owner_grant_rejects_foreign_privileged_disabled_and_deleted_targets(self):
        self.client.force_authenticate(self.admin_a)
        self.own_account.is_active = False
        self.own_account.save()
        for target in (self.foreign_owner, self.superuser, self.admin_b, self.own_account):
            for identifier in ({"user": target.pk}, {"username": target.username}):
                with self.subTest(target=target.username, identifier=identifier):
                    response = self.client.post("/api/v1/management/memberships/", {
                        **identifier, "role": "owner", "active": True,
                    }, format="json")
                    self.assertEqual(response.status_code, 403, response.data)
        self.own_account.is_active = True
        self.own_account.save()
        AccountProfile.objects.filter(user=self.own_account).update(deleted_at=timezone.now())
        response = self.client.post("/api/v1/management/memberships/", {
            "user": self.own_account.pk, "role": "owner",
        }, format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(is_owner(self.own_account))
        self.assertFalse(AuditEvent.objects.filter(action="membership.updated").exists())

    def test_owner_grant_allows_creator_and_superuser_without_resetting_password(self):
        self.own_account.set_password("Original-Strong-2026!")
        self.own_account.save()
        for actor, target in ((self.admin_a, self.own_account), (self.superuser, self.outsider)):
            self.client.force_authenticate(actor)
            response = self.client.post("/api/v1/management/memberships/", {
                "user": target.pk, "role": "owner", "active": True,
            }, format="json")
            self.assertEqual(response.status_code, 200, response.data)
            self.assertTrue(is_owner(target))
        self.own_account.refresh_from_db()
        self.assertTrue(self.own_account.check_password("Original-Strong-2026!"))

    def test_collaborator_injection_rejected_on_create_put_and_patch_atomically(self):
        super_owner = self.superuser
        grant_owner(super_owner)
        deleted_owner = get_user_model().objects.create_user("deleted_owner")
        grant_owner(deleted_owner)
        AccountProfile.objects.create(user=deleted_owner, created_by=self.owner, deleted_at=timezone.now())
        for target in (self.superuser, self.admin_b, self.outsider, self.foreign_owner, deleted_owner):
            for method in ("post", "put", "patch"):
                with self.subTest(target=target.username, method=method):
                    url = "/api/v1/competitions/"
                    if method != "post":
                        url += f"{self.batch.competition_id}/"
                    # Supply all required PUT fields so relation validation is exercised.
                    payload = {"name": "越权写入", "collaborators": [self.owner.pk, target.pk]}
                    if method == "post":
                        payload = self.competition_payload(**payload)
                    elif method == "put":
                        payload["departments"] = [department.pk for department in self.departments]
                    response = getattr(self.client, method)(url, payload, format="json")
                    self.assertEqual(response.status_code, 400, response.data)
                    self.assertEqual(Competition.objects.count(), 1)
                    self.batch.competition.refresh_from_db()
                    self.assertEqual(self.batch.competition.name, "测试竞赛")
                    self.assertEqual(list(self.batch.competition.collaborators.all()), [self.owner])
        self.assertFalse(AuditEvent.objects.filter(action__in=["competition.created", "competition.updated"]).exists())

    def test_collaborator_options_and_write_scope_match(self):
        grant_owner(self.own_account)
        self.client.force_authenticate(self.admin_a)
        options = {item["id"] for item in self.client.get("/api/v1/users/").data}
        self.assertIn(self.own_account.pk, options)
        self.assertNotIn(self.foreign_owner.pk, options)
        self.assertNotIn(self.superuser.pk, options)
        response = self.client.post("/api/v1/competitions/", self.competition_payload(
            collaborators=[self.own_account.pk],
        ), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(set(response.data["collaborators"]), {self.admin_a.pk, self.own_account.pk})
        self.client.force_authenticate(self.superuser)
        self.assertNotIn(self.outsider.pk, {item["id"] for item in self.client.get("/api/v1/users/").data})
        response = self.client.post("/api/v1/competitions/", self.competition_payload(
            collaborators=[self.foreign_owner.pk],
        ), format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_disabled_or_role_revoked_collaborator_cannot_be_assigned(self):
        grant_owner(self.own_account)
        AccountProfile.objects.filter(user=self.own_account).update(created_by=self.owner)
        self.own_account.is_active = False
        self.own_account.save()
        for active in (False, True):
            self.own_account.is_active = active
            self.own_account.save()
            if active:
                self.own_account.groups.clear()
            response = self.client.post("/api/v1/competitions/", self.competition_payload(
                collaborators=[self.own_account.pk],
            ), format="json")
            self.assertEqual(response.status_code, 400, response.data)

    def test_stale_collaborator_relation_does_not_grant_business_access(self):
        self.batch.competition.collaborators.add(self.outsider)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f"/api/v1/competitions/{self.batch.competition_id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/batches/{self.batch.pk}/detail/").status_code, 404)
        self.assertEqual(self.client.patch(f"/api/v1/competitions/{self.batch.competition_id}/", {
            "name": "旧协作关系越权",
        }, format="json").status_code, 404)
        self.owner.groups.remove(*self.owner.groups.filter(name=OWNER_GROUP))
        self.client.force_authenticate(self.owner)
        self.assertEqual(self.client.get(f"/api/v1/competitions/{self.batch.competition_id}/").status_code, 404)

    def test_competition_create_requires_role_and_admin_own_department(self):
        for actor, expected in ((self.outsider, 403), (self.admin_b, 403), (self.owner, 201)):
            self.client.force_authenticate(actor)
            response = self.client.post("/api/v1/competitions/", self.competition_payload(), format="json")
            self.assertEqual(response.status_code, expected, response.data)

    def test_emergency_issue_rejects_invalid_credentials_and_reason_without_writes(self):
        cases = (
            (self.owner, {"password": "Test-Pass-2026", "reason": "测试"}, 403),
            (self.superuser, {"reason": "测试"}, 403),
            (self.superuser, {"password": "wrong", "reason": "测试"}, 403),
            (self.superuser, {"password": "Test-Pass-2026", "reason": "  "}, 400),
            (self.superuser, {"password": "Test-Pass-2026", "reason": None}, 400),
            (self.superuser, {"password": [], "reason": "测试"}, 403),
        )
        for actor, payload, expected in cases:
            with self.subTest(actor=actor.username, payload=payload):
                self.client.force_authenticate(actor)
                response = self.client.post(f"/api/v1/batches/{self.batch.pk}/emergency-issue/", payload, format="json")
                self.assertEqual(response.status_code, expected, response.data)
                self.batch.refresh_from_db()
                self.assertEqual(self.batch.status, AwardBatch.Status.DRAFT)
                self.assertFalse(GenerationTask.objects.exists())
                self.assertFalse(AuditEvent.objects.filter(action="emergency.issue").exists())

    def test_queued_and_running_work_blocks_competition_archive(self):
        self.client.force_authenticate(self.superuser)
        for status in ("queued", "running"):
            GenerationTask.objects.update_or_create(version=self.version, defaults={"status": status})
            self.batch.status = AwardBatch.Status.QUEUED
            self.batch.save()
            with self.subTest(status=status):
                response = self.client.patch(f"/api/v1/competitions/{self.batch.competition_id}/", {"active": False}, format="json")
                self.assertEqual(response.status_code, 400, response.data)
                self.assertEqual(self.client.delete(f"/api/v1/competitions/{self.batch.competition_id}/").status_code, 400)
                self.assertEqual(self.client.delete(f"/api/v1/batches/{self.batch.pk}/").status_code, 400)

    def test_csrf_requires_token_with_session_authentication(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.owner)
        response = client.post("/api/v1/competitions/", self.competition_payload(), format="json")
        self.assertEqual(response.status_code, 403, response.data)
        self.assertIn("CSRF", str(response.data))
        token = client.get("/api/v1/auth/csrf/").data["csrfToken"]
        response = client.post("/api/v1/competitions/", self.competition_payload(), format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code, 201, response.data)

    def test_seal_denial_does_not_invalidate_the_backend_session(self):
        client = APIClient()
        client.force_login(self.owner)
        self.assertEqual(client.get("/api/v1/seals/").status_code, 403)
        self.assertEqual(client.get("/api/v1/auth/me/").status_code, 200)
        self.assertEqual(int(client.session["_auth_user_id"]), self.owner.pk)

    def test_emergency_void_rejects_invalid_reason_and_password_types(self):
        self.client.force_authenticate(self.superuser)
        certificate = Certificate.objects.create(award=self.award, number="EMERGENCY-TYPE-TEST", published_at=timezone.now())
        for payload, expected in (
            ({"password": "Test-Pass-2026", "reason": None}, 400),
            ({"password": [], "reason": "复测"}, 403),
        ):
            with self.subTest(payload=payload):
                response = self.client.post(f"/api/v1/certificates/{certificate.pk}/emergency_void/", payload, format="json")
                self.assertEqual(response.status_code, expected, response.data)
                certificate.refresh_from_db()
                self.assertEqual(certificate.status, Certificate.Status.ACTIVE)
        self.assertFalse(AuditEvent.objects.filter(action="emergency.void").exists())
