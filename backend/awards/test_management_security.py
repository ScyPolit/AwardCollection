import copy
import hashlib
import io
import zipfile
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient
from . import tests as fixtures
from .models import AccountProfile, Certificate, Notification, TemplateVersion
from .services import submit_batch, decide
from .integrity import verify
from .presentation import validate_presentation
from .template_import import check_office_archive, import_file
from .realtime import snapshot_for


class ManagementSecurityTests(TestCase):
    def setUp(self):
        fixtures.WorkflowTests.setUp(self)
        self.client = APIClient()
        self.client.force_authenticate(self.superuser)

    def test_account_management_scoped_to_creator(self):
        AccountProfile.objects.create(user=self.owner, created_by=self.admin_a)
        self.client.force_authenticate(self.admin_b)
        self.assertEqual(
            self.client.patch(
                f"/api/v1/management/accounts/{self.owner.pk}/",
                {"name": "越权修改"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/management/accounts/{self.owner.pk}/"
            ).status_code,
            403,
        )
        self.client.force_authenticate(self.admin_a)
        result = self.client.patch(
            f"/api/v1/management/accounts/{self.owner.pk}/",
            {"name": "正式姓名", "email": "owner@example.test"},
            format="json",
        )
        self.assertEqual(result.status_code, 200, result.data)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.first_name, "正式姓名")

    def test_account_delete_hides_and_disables_without_losing_authorship(self):
        result = self.client.delete(f"/api/v1/management/accounts/{self.owner.pk}/")
        self.assertEqual(result.status_code, 204)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.is_active)
        self.assertNotIn(
            self.owner.pk,
            [u["id"] for u in self.client.get("/api/v1/management/accounts/").data],
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.created_by_id, self.owner.pk)
        self.assertEqual(
            self.client.delete(
                f"/api/v1/management/accounts/{self.superuser.pk}/"
            ).status_code,
            403,
        )

    def test_notification_mutations_only_affect_current_user(self):
        own = Notification.objects.create(
            user=self.superuser, title="own", body="text", target="/business/batches"
        )
        other = Notification.objects.create(
            user=self.owner, title="private", body="private data"
        )
        self.assertEqual(
            self.client.patch(
                f"/api/v1/notifications/{other.pk}/", {"read_at": None}, format="json"
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/notifications/",
                {"user": self.owner.pk, "title": "forged"},
                format="json",
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/v1/notifications/read_all/", {}, format="json"
            ).status_code,
            200,
        )
        own.refresh_from_db()
        other.refresh_from_db()
        self.assertIsNotNone(own.read_at)
        self.assertIsNone(other.read_at)
        self.assertEqual(
            self.client.delete(f"/api/v1/notifications/{own.pk}/").status_code, 204
        )

    def test_realtime_snapshot_is_private_and_respects_disabled_accounts(self):
        Notification.objects.create(user=self.owner, title="owner only", body="private")
        Notification.objects.create(
            user=self.outsider, title="outsider only", body="private"
        )
        state = snapshot_for(self.owner.pk)
        self.assertEqual([n["title"] for n in state["notifications"]], ["owner only"])
        self.assertEqual(state["jobs"], [])
        self.owner.is_active = False
        self.owner.save()
        self.assertIsNone(snapshot_for(self.owner.pk))

    def test_award_tamper_blocks_approval(self):
        submit_batch(self.batch.pk, self.owner)
        self.award.award_name = "篡改的特等奖"
        self.award.save()
        with self.assertRaisesMessage(ValueError, "完整性"):
            decide(
                self.version.required_departments.first().pk, self.admin_a, "approved"
            )

    def test_frozen_template_tamper_is_detected(self):
        submit_batch(self.batch.pk, self.owner)
        self.version.refresh_from_db()
        self.version.snapshot = {"template": {"title": "tampered"}}
        self.version.save()
        with self.assertRaisesMessage(ValueError, "完整性"):
            verify(self.version)

    def test_seal_file_tamper_blocks_submission(self):
        requirement = self.version.required_departments.first()
        Path(requirement.seal_version.image.path).write_bytes(b"tampered")
        with self.assertRaisesMessage(ValueError, "公章文件完整性"):
            submit_batch(self.batch.pk, self.owner)

    def test_certificate_file_tamper_blocks_download(self):
        from django.core.files.base import ContentFile
        from django.utils import timezone

        certificate = Certificate.objects.create(
            award=self.award,
            number="TEST-INTEGRITY",
            published_at=timezone.now(),
            pdf=ContentFile(b"tampered", name="test.pdf"),
            pdf_sha256=hashlib.sha256(b"original").hexdigest(),
        )
        self.assertEqual(
            self.client.get(
                f"/api/v1/certificates/{certificate.pk}/download/pdf/"
            ).status_code,
            409,
        )

    def test_rows_crud_and_optimistic_version(self):
        url = f"/api/v1/batches/{self.batch.pk}/rows/"
        response = self.client.post(
            url,
            {
                "operation": "update",
                "source_row": 2,
                "expected_version": 1,
                "row": {"team_name": "已更正"},
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["version"], 2)
        self.assertEqual(
            self.client.post(
                url,
                {"operation": "delete", "source_row": 2, "expected_version": 1},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                url,
                {"operation": "delete", "source_row": 2, "expected_version": 2},
                format="json",
            ).status_code,
            200,
        )
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.versions.get(number=3).awards.count(), 0)

    def test_rows_and_excel_are_frozen_during_review(self):
        submit_batch(self.batch.pk, self.owner)
        self.assertEqual(
            self.client.post(
                f"/api/v1/batches/{self.batch.pk}/rows/",
                {"operation": "delete", "source_row": 2, "expected_version": 1},
                format="json",
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                f"/api/v1/batches/{self.batch.pk}/import/", {}, format="multipart"
            ).status_code,
            400,
        )

    def test_template_version_prevents_overwriting_other_editor(self):
        template = self.version.template_version.template
        url = f"/api/v1/templates/{template.pk}/save_version/"
        self.assertEqual(
            self.client.post(
                url, {"canvas": {}, "expected_version": 1}, format="json"
            ).status_code,
            201,
        )
        self.assertEqual(
            self.client.post(
                url,
                {"canvas": {"title": "stale"}, "expected_version": 1},
                format="json",
            ).status_code,
            409,
        )
        self.assertEqual(template.versions.count(), 2)

    def test_archiving_never_mutates_issued_original(self):
        self.assertEqual(
            self.client.delete(
                f"/api/v1/templates/{self.version.template_version.template_id}/"
            ).status_code,
            204,
        )
        self.assertEqual(self.client.get("/api/v1/templates/").data, [])
        self.assertTrue(
            TemplateVersion.objects.filter(pk=self.version.template_version_id).exists()
        )

    def test_office_import_rejects_external_links_macros_and_zip_bombs(self):
        for filename, content in [
            ("ppt/vbaProject.bin", b"macro"),
            (
                "ppt/_rels/presentation.xml.rels",
                b'<Relationships><Relationship TargetMode="External" Target="http://127.0.0.1/" /></Relationships>',
            ),
            ("../escape", b"test"),
        ]:
            data = io.BytesIO()
            with zipfile.ZipFile(data, "w") as archive:
                archive.writestr(filename, content)
            with self.assertRaises(ValueError):
                check_office_archive(data.getvalue())

    def test_unknown_import_and_office_header_rejected(self):
        for name in ["template.exe", "template.ppt", "template.pptx"]:
            with self.assertRaises(ValueError):
                import_file(SimpleUploadedFile(name, b"invalid"))
        self.client.force_authenticate(self.outsider)
        result = self.client.post(
            "/api/v1/templates/import_file/",
            {"file": SimpleUploadedFile("template.pptx", b"invalid")},
            format="multipart",
        )
        self.assertEqual(result.status_code, 403)

    def test_pptist_sanitizes_html_and_preserves_indent_and_spaces(self):
        canvas = {
            "engine": "pptist",
            "page": {"width": 842, "height": 595},
            "slideIndex": 0,
            "presentation": {
                "viewportSize": 842,
                "viewportRatio": 595 / 842,
                "slides": [
                    {
                        "id": "one",
                        "elements": [
                            {
                                "id": "text",
                                "type": "text",
                                "left": 10,
                                "top": 20,
                                "width": 600,
                                "height": 100,
                                "content": '<p style="text-indent:2em"><span style="font-family:AC_hei;font-size:24px">张三   同学</span><img onerror="alert(1)" src=x></p>',
                            }
                        ],
                    }
                ],
            },
        }
        cleaned = validate_presentation(canvas)["presentation"]["slides"][0][
            "elements"
        ][0]["content"]
        self.assertIn("text-indent:2em", cleaned)
        self.assertIn("张三   同学", cleaned)
        self.assertNotIn("onerror", cleaned)
        bad = copy.deepcopy(canvas)
        bad["presentation"]["slides"][0]["elements"][0][
            "src"
        ] = "http://127.0.0.1/private"
        with self.assertRaises(ValueError):
            validate_presentation(bad)

    def test_audit_logs_cannot_be_modified_or_deleted(self):
        from .models import AuditEvent

        event = AuditEvent.objects.create(
            actor=self.owner, action="test", object_type="test", object_id="test"
        )
        self.assertIn(
            self.client.delete(f"/api/v1/logs/{event.pk}/").status_code, [403, 405]
        )
        self.assertIn(
            self.client.patch(
                f"/api/v1/logs/{event.pk}/", {"detail": {}}, format="json"
            ).status_code,
            [403, 405],
        )

    def test_authorized_cleanup_preserves_template_and_materials(self):
        from django.core.management import call_command
        from .management.commands.clear_demo_business import canvas_digest
        from .services import allocate_number
        from .models import CertificateSequence, Competition, Department, AwardBatch

        template = self.version.template_version.template
        before = canvas_digest(self.version.template_version.canvas)
        number = allocate_number()
        next_value = CertificateSequence.objects.first().next_value
        call_command(
            "clear_demo_business",
            template_id=template.pk,
            superuser_id=self.superuser.pk,
            expected_template_sha256=before,
            verified_backup="/opt/awardcollection-v1-test/backups/test-verified",
            apply=True,
            stdout=io.StringIO(),
        )
        self.assertEqual(
            list(get_user_model().objects.values_list("pk", flat=True)),
            [self.superuser.pk],
        )
        self.assertEqual(Competition.objects.count(), 0)
        self.assertEqual(AwardBatch.objects.count(), 0)
        template.refresh_from_db()
        self.assertEqual(template.name, "标准模板")
        self.assertEqual(template.created_by_id, self.superuser.pk)
        self.assertEqual(canvas_digest(template.versions.first().canvas), before)
        self.assertTrue(Department.objects.filter(pk=template.department_id).exists())
        self.assertEqual(CertificateSequence.objects.first().next_value, next_value)

    def test_read_receipt_is_persisted_idempotently_and_reflected_in_stream(self):
        notice=Notification.objects.create(user=self.superuser,title='test',body='test')
        url=f'/api/v1/notifications/{notice.pk}/'
        first=self.client.patch(url,{'read_at':True},format='json')
        self.assertEqual(first.status_code,200);self.assertEqual(first.data['unreadCount'],0)
        second=self.client.patch(url,{'read_at':None},format='json')
        self.assertEqual(first.data['read_at'],second.data['read_at'])
        state=snapshot_for(self.superuser.pk);self.assertEqual(state['unread'],0);self.assertIsNotNone(state['notifications'][0]['read_at'])

    def test_valid_pptx_accepts_empty_embeddings_directory(self):
        data=io.BytesIO()
        with zipfile.ZipFile(data,'w') as archive:
            archive.writestr('ppt/embeddings/','')
            archive.writestr('ppt/presentation.xml','<presentation />')
        response=import_file(SimpleUploadedFile('template.pptx',data.getvalue()))
        self.assertEqual(response['filename'],'template.pptx')

    def test_generation_retry_requires_complete_unmodified_approval(self):
        from .models import GenerationTask
        submit_batch(self.batch.pk,self.owner)
        requirements=list(self.version.required_departments.order_by('department_id'))
        decide(requirements[0].pk,self.admin_a,'approved');task=decide(requirements[1].pk,self.admin_b,'approved')
        task.status='failed';task.save()
        url=f'/api/v1/batches/{self.batch.pk}/retry_generation/'
        self.assertEqual(self.client.post(url,{},format='json').status_code,200)
        task.refresh_from_db();self.assertEqual(task.status,'queued')
        task.status='failed';task.save();self.award.award_name='篡改奖项';self.award.save()
        self.assertEqual(self.client.post(url,{},format='json').status_code,400)

    def test_login_rejects_missing_csrf_but_accepts_valid_same_origin_token(self):
        client=APIClient(enforce_csrf_checks=True)
        payload={'username':self.owner.username,'password':'Test-Pass-2026'}
        self.assertEqual(client.post('/api/v1/auth/login/',payload,format='json').status_code,403)
        csrf=client.get('/api/v1/auth/csrf/').data['csrfToken']
        response=client.post('/api/v1/auth/login/',payload,format='json',HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(response.status_code,200,response.content[:200])

    def test_historical_certificate_keeps_frozen_competition_name(self):
        from django.utils import timezone
        self.version.snapshot={'competition':{'id':self.batch.competition_id,'name':'签发时竞赛名称'}};self.version.save()
        certificate=Certificate.objects.create(award=self.award,number='TEST-FROZEN-NAME',published_at=timezone.now())
        competition=self.batch.competition;competition.name='之后修改的名称';competition.save()
        data=self.client.get(f'/api/v1/certificates/{certificate.pk}/').data
        self.assertEqual(data['competition_name'],'签发时竞赛名称')
        verified=self.client.post('/api/v1/verification/admin/',{'number':certificate.number},format='json')
        self.assertEqual(verified.data['competition'],'签发时竞赛名称')

    def test_corrupt_native_images_are_rejected_before_rendering(self):
        from .presentation import _image
        with self.assertRaises(ValueError):_image('data:image/png;base64,AAAA')
        with self.assertRaises(ValueError):_image('data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9ImFsZXJ0KDEpIiAvPg==')

    def test_malformed_public_inputs_are_validation_errors(self):
        client=APIClient()
        self.assertEqual(client.post('/api/v1/auth/login/',{'username':{},'password':[]},format='json').status_code,400)
        self.assertEqual(client.post('/api/v1/verification/query/',{'number':'x'*1000},format='json').status_code,400)

    async def test_asgi_download_uses_bounded_async_chunks(self):
        from django.test import AsyncClient
        client=AsyncClient()
        await client.aforce_login(self.superuser)
        response=await client.get('/api/v1/fonts/hei/file/')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.is_async)
        count=0;total=0
        async for chunk in response.streaming_content:
            count+=1;total+=len(chunk);self.assertLessEqual(len(chunk),65536)
        self.assertGreater(count,1);self.assertEqual(total,int(response['Content-Length']))
