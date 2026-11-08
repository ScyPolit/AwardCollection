import hashlib
import io
import json
import tempfile
import uuid
import zipfile
from pathlib import Path
from unittest.mock import patch
from django.core.files.base import ContentFile
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from . import tests as fixtures
from .models import Certificate, TeamAward, BatchVersion, ApprovalDepartment, PreparedFile, Notification, DepartmentMembership
from .prepared import request_file, claim_file, process_file, build_zip, status_data
from .realtime import snapshot_for


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class PerformancePermissionTests(TestCase):
    def setUp(self):
        fixtures.WorkflowTests.setUp(self)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)

    def certificate(self, version=None, index=1):
        version = version or self.version
        award = self.award if index == 1 and version == self.version else TeamAward.objects.create(version=version, source_row=index+10, members=["测试成员"], award_name="一等奖", last_edited_by=self.owner)
        certificate = Certificate.objects.create(award=award, number=f"TEST-{version.pk}-{index}", published_at=timezone.now())
        pdf, png = b"%PDF-TEST-ONLY", b"PNG-TEST-ONLY"
        certificate.pdf.save(certificate.number+".pdf", ContentFile(pdf), save=False)
        certificate.image.save(certificate.number+".png", ContentFile(png), save=False)
        certificate.pdf_sha256 = hashlib.sha256(pdf).hexdigest()
        certificate.image_sha256 = hashlib.sha256(png).hexdigest()
        certificate.save()
        return certificate

    def test_owner_can_use_editor_fonts_but_not_manage_seals_or_font_library(self):
        for path in ('seals/', 'fonts/?include_inactive=1'):
            self.assertEqual(self.client.get('/api/v1/'+path).status_code, 403)
        self.assertEqual(self.client.get('/api/v1/fonts/').status_code, 200)
        self.assertEqual(self.client.post('/api/v1/fonts/', {}, format='multipart').status_code, 400)
        self.client.force_authenticate(self.admin_a)
        seals = self.client.get('/api/v1/seals/').data
        self.assertEqual({s['department'] for s in seals}, {self.departments[0].pk})
        other = self.version.required_departments.get(department=self.departments[1]).seal_version.seal
        self.assertEqual(self.client.get(f'/api/v1/seals/{other.pk}/preview/').status_code, 404)
        self.assertEqual(self.client.patch(f'/api/v1/seals/{other.pk}/', {'name':'侵入'},format='json').status_code,404)

    def test_permissions_follow_frozen_approval_not_current_competition_departments(self):
        # Same competition, a different batch version requiring only department B.
        version = BatchVersion.objects.create(batch=self.batch, number=2, template_version=self.version.template_version)
        requirement = self.version.required_departments.get(department=self.departments[1])
        ApprovalDepartment.objects.create(version=version, department=requirement.department, seal_version=requirement.seal_version)
        certificate = self.certificate(version)
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.get('/api/v1/certificates/').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/v1/certificates/{certificate.pk}/').status_code,404)
        self.assertEqual(self.client.get(f'/api/v1/certificates/{certificate.pk}/download/pdf/').status_code,403)
        self.assertFalse(self.client.post('/api/v1/verification/admin/', {'number':certificate.number},format='json').data['found'])
        self.client.force_authenticate(self.admin_b)
        self.assertEqual(self.client.get('/api/v1/certificates/').data['count'],1)

    def test_batch_scope_and_notifications_rechecked_after_department_role_changes(self):
        certificate = self.certificate()
        asset = request_file(self.admin_a,'batch_zip',batch_id=self.batch.pk)
        Notification.objects.create(user=self.admin_a,title='待办',body='本部门信息',target=f'/business/batches?batch={self.batch.pk}')
        DepartmentMembership.objects.filter(user=self.admin_a).update(active=False)
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.get(f'/api/v1/prepared-files/{asset.pk}/').status_code,403)
        self.assertEqual(self.client.get('/api/v1/notifications/').data, [])
        self.assertEqual(snapshot_for(self.admin_a.pk)['jobs'], [])

    def test_historical_approval_does_not_grant_current_competition_write_permission(self):
        competition=self.batch.competition
        competition.departments.set([self.departments[1]])
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.client.get(f'/api/v1/competitions/{competition.pk}/').status_code,200)
        self.assertEqual(self.client.patch(f'/api/v1/competitions/{competition.pk}/',{'name':'越权'},format='json').status_code,403)
        self.assertEqual(self.client.delete(f'/api/v1/competitions/{competition.pk}/').status_code,403)

    def test_legacy_revocation_notice_is_scoped_after_department_change(self):
        from .models import RevocationRequest
        certificate=self.certificate()
        request=RevocationRequest.objects.create(certificate=certificate,requested_by=self.owner,reason='测试')
        Notification.objects.create(user=self.admin_a,title='证书作废审批',body='测试',target=f'/business/approvals?revocation={request.pk}')
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(len(self.client.get('/api/v1/notifications/').data),1)
        DepartmentMembership.objects.filter(user=self.admin_a).update(active=False)
        self.assertEqual(self.client.get('/api/v1/notifications/').data,[])

    def test_archive_is_queued_deduplicated_persisted_and_authorized(self):
        certificate = self.certificate()
        data={'kind':'batch_zip','batch':self.batch.pk}
        first=self.client.post('/api/v1/prepared-files/',data,format='json')
        self.assertEqual(first.status_code,202,first.data)
        again=self.client.post('/api/v1/prepared-files/',data,format='json')
        self.assertEqual(first.data['id'],again.data['id'])
        asset=process_file(claim_file())
        self.assertEqual(asset.status,'ready',asset.error)
        with zipfile.ZipFile(asset.file.path) as bundle:
            self.assertEqual(set(bundle.namelist()),{certificate.number+'.pdf',certificate.number+'.png'})
        response=self.client.get(f'/api/v1/prepared-files/{asset.pk}/download/')
        self.assertEqual(response.status_code,200)
        self.assertGreater(len(b''.join(response.streaming_content)),20)
        self.client.force_authenticate(self.outsider)
        self.assertEqual(self.client.get(f'/api/v1/prepared-files/{asset.pk}/download/').status_code,403)

    def test_archive_query_never_selects_template_snapshot_or_related_objects(self):
        self.version.snapshot={'template':{'background':'A'*(2*1024*1024)}}
        self.version.save()
        for i in range(1,8):self.certificate(index=i)
        asset=claim_file() if PreparedFile.objects.exists() else None
        asset=request_file(self.owner,'batch_zip',batch_id=self.batch.pk)
        asset=claim_file()
        with CaptureQueriesContext(connection) as queries:
            result=process_file(asset)
        self.assertEqual(result.status,'ready',result.error)
        selects=[q['sql'] for q in queries if q['sql'].lstrip().upper().startswith('SELECT')]
        self.assertFalse(any('"snapshot"' in sql or '"canvas"' in sql for sql in selects),selects)

    def test_modified_source_is_not_packaged_and_old_package_is_invalidated(self):
        certificate=self.certificate()
        request_file(self.owner,'batch_zip',batch_id=self.batch.pk)
        asset=process_file(claim_file())
        certificate.notes='管理信息更新';certificate.save()
        self.assertEqual(self.client.get(f'/api/v1/prepared-files/{asset.pk}/download/').status_code,409)
        Path(certificate.pdf.path).write_bytes(b'tampered')
        next_asset=request_file(self.owner,'batch_zip',batch_id=self.batch.pk)
        result=process_file(claim_file())
        self.assertEqual(result.status,'failed')
        self.assertFalse(result.file)

    def test_accel_redirect_is_protected_and_does_not_read_file_into_response(self):
        certificate=self.certificate()
        with override_settings(USE_ACCEL_DOWNLOAD=True):
            response=self.client.get(f'/api/v1/certificates/{certificate.pk}/download/pdf/')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response['X-Accel-Redirect'].startswith('/_protected-downloads/certificates/'))
        self.assertEqual(response['X-Accel-Limit-Rate'], '0')
        self.assertEqual(response.content,b'')

    def test_template_list_is_metadata_only_and_batch_detail_is_paginated(self):
        template=self.version.template_version
        template.canvas={'background':'A'*(2*1024*1024),'page':{'width':842,'height':595}}
        template.save()
        response=self.client.get('/api/v1/templates/')
        self.assertLess(len(response.content),4000)
        self.assertNotIn('canvas',response.data[0]['latest_version'])
        TeamAward.objects.bulk_create([TeamAward(version=self.version,source_row=i+10,members=['测试'],award_name='一等奖',last_edited_by=self.owner) for i in range(60)])
        response=self.client.get(f'/api/v1/batches/{self.batch.pk}/detail/?page=2&page_size=50')
        self.assertEqual(response.data['award_count'],61)
        self.assertEqual(len(response.data['awards']),11)

    def test_preview_is_queued_without_rendering_in_the_api_process(self):
        with patch('awards.renderer.render_unsigned', side_effect=AssertionError('API must not render')):
            response=self.client.get(f'/api/v1/batches/{self.batch.pk}/preview/')
        self.assertEqual(response.status_code,200)
        self.assertIn('正在准备文件',response.content.decode())
        self.assertEqual(PreparedFile.objects.get().kind,'batch_preview')

    def test_worker_spawn_generates_and_resumes_png_without_rewriting_signed_pdf(self):
        from .services import submit_batch, decide, claim_task
        from .management.commands.runworker import process_task
        from .models import GenerationTask
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGBA', (40,40), (200,0,0,100)).save(buffer, format='PNG')
        for requirement in self.version.required_departments.select_related('seal_version'):
            seal = requirement.seal_version
            seal.image.save('valid.png', ContentFile(buffer.getvalue()), save=False)
            seal.sha256 = hashlib.sha256(buffer.getvalue()).hexdigest()
            seal.save()
        self.version.output_formats=['pdf','png'];self.version.save()
        submit_batch(self.batch.pk,self.owner)
        requirements=list(self.version.required_departments.order_by('department_id'))
        decide(requirements[0].pk,self.admin_a,'approved')
        decide(requirements[1].pk,self.admin_b,'approved')
        with patch.dict('os.environ',{'RENDER_CONCURRENCY':'1'}):
            result=process_task(claim_task())
        self.assertEqual(result.status,'done')
        certificate=Certificate.objects.get(award=self.award)
        original=Path(certificate.pdf.path).read_bytes()
        self.assertTrue(certificate.published_at)
        self.assertTrue(Path(certificate.image.path).is_file())
        from pyhanko.pdf_utils.reader import PdfFileReader
        from pyhanko.sign.validation import validate_pdf_signature
        reader=PdfFileReader(io.BytesIO(original))
        self.assertEqual(len(reader.embedded_signatures),2)
        for signature in reader.embedded_signatures:
            status=validate_pdf_signature(signature)
            self.assertTrue(status.intact and status.valid)
        Path(certificate.image.path).unlink()
        certificate.image='';certificate.image_sha256='';certificate.save()
        GenerationTask.objects.filter(pk=result.pk).update(status='queued',lease_expires_at=None)
        with patch.dict('os.environ',{'RENDER_CONCURRENCY':'1'}):
            process_task(claim_task())
        certificate.refresh_from_db()
        self.assertEqual(Path(certificate.pdf.path).read_bytes(),original)
        self.assertTrue(Path(certificate.image.path).is_file())

    def test_large_page_image_has_bounded_pixels(self):
        import pymupdf as fitz
        from .renderer import image_from_pdf
        from PIL import Image
        root=Path(self.media_directory.name)
        with fitz.open() as document:
            document.new_page(width=12000,height=9000)
            document.save(root/'large.pdf')
        with patch.dict('os.environ',{'CERTIFICATE_IMAGE_MAX_PIXELS':'1000000'}):
            image_from_pdf(root/'large.pdf',root/'large.png')
        with Image.open(root/'large.png') as image:
            self.assertLess(image.width*image.height,1_005_000)

    def test_archive_formats_and_expired_leases_are_bounded(self):
        from datetime import timedelta
        self.certificate()
        self.version.output_formats=['png'];self.version.save()
        asset=request_file(self.owner,'batch_zip',batch_id=self.batch.pk)
        asset=claim_file()
        token=asset.lease_token
        PreparedFile.objects.filter(pk=asset.pk).update(lease_expires_at=timezone.now()-timedelta(seconds=1))
        replacement=claim_file()
        self.assertNotEqual(replacement.lease_token,token)
        result=process_file(asset)
        self.assertEqual(result.status,'running')
        result=process_file(replacement)
        self.assertEqual(result.status,'ready',result.error)
        with zipfile.ZipFile(result.file.path) as bundle:
            self.assertEqual(len(bundle.namelist()),1)
            self.assertTrue(bundle.namelist()[0].endswith('.png'))
