import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch
from django.core.management import call_command
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from . import tests as test_fixtures
from .models import ApprovalDecision, Certificate, CertificateFont, GenerationTask, PreparedFile, Template, TemplateVersion, VerificationRateLimit, AuditEvent
from .services import allocate_number, submit_batch, decide, withdraw_approval
from .verification import reserve_query
from .fonts import font_catalog


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class DeliveryTests(TestCase):
    setUp = test_fixtures.WorkflowTests.setUp

    def client_as(self, actor=None):
        client = APIClient()
        if actor:
            client.force_authenticate(actor)
        return client

    def certificate(self, number='2026-AC-00000001'):
        return Certificate.objects.create(award=self.award, number=number, published_at=timezone.now())

    def approve(self, all_departments=True):
        submit_batch(self.batch.pk, self.owner)
        rows = list(self.version.required_departments.order_by('department_id'))
        decide(rows[0].pk, self.admin_a, 'approved', '批准意见')
        if all_departments:
            decide(rows[1].pk, self.admin_b, 'approved')
        return rows

    def test_new_number_and_legacy_lookup_without_captcha(self):
        self.assertRegex(allocate_number(), r'^\d{4}AC\d{8}$')
        self.certificate()
        result = self.client_as().post('/api/v1/verification/query/', {'number':'2026ac00000001'}, format='json')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['number'], '2026-AC-00000001')
        self.assertEqual(result.data['members'], ['张*','李*'])
        self.assertTrue(result.data['watermark_text'])
        self.assertNotIn('teachers',result.data)

    def test_new_number_also_accepts_legacy_style_input(self):
        self.certificate('2026AC00000001')
        answer = self.client_as().post('/api/v1/verification/query/', {'number':'2026-AC-00000001'},format='json')
        self.assertTrue(answer.data['found'])

    def test_public_and_internal_share_sixty_query_budget(self):
        public, internal = self.client_as(), self.client_as(self.superuser)
        for index in range(60):
            client, endpoint = (public,'query') if index % 2 else (internal,'admin')
            response = client.post(f'/api/v1/verification/{endpoint}/',{'number':'2026AC00000000'},format='json')
            self.assertEqual(response.status_code,200)
        limited=public.post('/api/v1/verification/query/',{'number':'2026AC00000000'},format='json')
        self.assertEqual(limited.status_code,429)
        self.assertGreaterEqual(int(limited['Retry-After']),1)

    def test_sliding_window_expires_and_ips_are_independent(self):
        with patch('awards.verification.time.time',return_value=1000):
            for _ in range(60):self.assertEqual(reserve_query('127.0.0.8'),0)
            self.assertEqual(reserve_query('127.0.0.8'),60)
            self.assertEqual(reserve_query('127.0.0.9'),0)
        with patch('awards.verification.time.time',return_value=1060.1):
            self.assertEqual(reserve_query('127.0.0.8'),0)

    def test_disclosure_settings_and_watermarks_follow_superuser_configuration(self):
        root=self.client_as(self.superuser)
        updated=root.put('/api/v1/settings/public-verification/',{'show_team':False,'show_members':False,'show_work':True,'show_teachers':True,'mask_teachers':False,'watermark_text':'学校证书查验专用'},format='json')
        self.assertEqual(updated.status_code,200)
        cert=self.certificate()
        answer=self.client_as().post('/api/v1/verification/query/',{'number':cert.number},format='json').data
        self.assertNotIn('team',answer);self.assertNotIn('members',answer)
        self.assertIn('work',answer);self.assertIn('teachers',answer)
        self.assertEqual(answer['watermark_text'],'学校证书查验专用')
        missing=self.client_as().post('/api/v1/verification/query/',{'number':'2026AC99999999'},format='json').data
        self.assertFalse(missing['found']);self.assertEqual(missing['watermark_text'],'学校证书查验专用')
        self.assertEqual(self.client_as(self.admin_a).get('/api/v1/settings/public-verification/').status_code,403)
        self.assertEqual(root.put('/api/v1/settings/public-verification/',{'show_members':'false'},format='json').status_code,400)
        self.assertEqual(root.put('/api/v1/settings/public-verification/',{'watermark_text':' '},format='json').status_code,400)

    def test_internal_lookup_keeps_department_scope(self):
        cert=self.certificate()
        from .models import DepartmentMembership
        DepartmentMembership.objects.filter(user=self.admin_b).delete()
        self.assertFalse(self.client_as(self.admin_b).post('/api/v1/verification/admin/',{'number':cert.number},format='json').data['found'])

    def test_owner_can_edit_shared_template_but_cannot_manage_others_template_or_seals(self):
        owner=self.client_as(self.owner);template=self.version.template_version.template
        detail=owner.get(f'/api/v1/templates/{template.pk}/')
        self.assertTrue(detail.data['can_edit']);self.assertFalse(detail.data['can_manage'])
        saved=owner.post(f'/api/v1/templates/{template.pk}/save_version/',{'expected_version':1,'canvas':{'title':'正式证书'}},format='json')
        self.assertEqual(saved.status_code,201)
        self.assertEqual(owner.patch(f'/api/v1/templates/{template.pk}/',{'published':False},format='json').status_code,403)
        self.assertEqual(owner.get('/api/v1/fonts/').status_code,200)
        self.assertEqual(owner.get('/api/v1/fonts/?include_inactive=1').status_code,403)
        self.assertEqual(owner.get('/api/v1/seals/').status_code,403)

    def test_font_priority_and_persisted_order_include_builtins(self):
        for name, char in [('宋体','a'),('华文行楷','b')]:
            CertificateFont.objects.create(sha256=char*64,name=name,file='unused.ttf',license_note='已授权',created_by=self.superuser)
        fonts=font_catalog()
        self.assertEqual([item['name'] for item in fonts[:2]],['华文行楷','宋体'])
        ids=[item['id'] for item in reversed(fonts)]
        response=self.client_as(self.superuser).post('/api/v1/fonts/order/',{'ids':ids},format='json')
        self.assertEqual(response.status_code,200)
        self.assertEqual([item['id'] for item in font_catalog()],ids)
        self.assertEqual(self.client_as(self.owner).post('/api/v1/fonts/order/',{'ids':ids},format='json').status_code,403)
        self.assertEqual(self.client_as(self.superuser).post('/api/v1/fonts/order/',{'ids':[ids[0],ids[0]]},format='json').status_code,400)

    def test_approved_tab_is_available_to_owner_without_withdraw_permission(self):
        rows=self.approve(False)
        result=self.client_as(self.owner).get('/api/v1/approvals/?scope=approved')
        self.assertEqual(result.status_code,200)
        self.assertEqual([item['id'] for item in result.data],[rows[0].pk])
        self.assertFalse(result.data[0]['can_withdraw'])
        self.assertEqual(self.client_as(self.owner).post(f'/api/v1/approvals/{rows[0].pk}/withdraw/',{'reason':'更正'},format='json').status_code,403)

    def test_withdraw_partial_approval_creates_clean_returned_revision(self):
        rows=self.approve(False)
        response=self.client_as(self.admin_a).post(f'/api/v1/approvals/{rows[0].pk}/withdraw/',{'reason':'审批误点'},format='json')
        self.assertEqual(response.status_code,200)
        self.batch.refresh_from_db();self.assertEqual(self.batch.status,'returned');self.assertEqual(self.batch.current_version,2)
        old=ApprovalDecision.objects.get(requirement=rows[0])
        self.assertEqual(old.actor,self.admin_a);self.assertEqual(old.decision,'withdrawn');self.assertEqual(old.comment,'批准意见')
        self.assertEqual(old.withdrawal_reason,'审批误点')
        self.assertFalse(self.batch.versions.get(number=2).required_departments.filter(decision__isnull=False).exists())
        duplicate=self.client_as(self.admin_a).post(f'/api/v1/approvals/{rows[0].pk}/withdraw/',{'reason':'再点一次'},format='json')
        self.assertEqual(duplicate.status_code,409);self.assertEqual(self.batch.versions.count(),2)

    def test_withdraw_queued_or_running_generation_invalidates_lease(self):
        rows=self.approve()
        task=GenerationTask.objects.get(version=self.version)
        import uuid
        task.status='running';task.lease_token=uuid.uuid4();task.save()
        token=task.lease_token
        withdraw_approval(rows[0].pk,self.superuser,'更正审批')
        task.refresh_from_db()
        self.assertEqual(task.status,'cancelled');self.assertNotEqual(task.lease_token,token)

    def test_withdraw_issued_batch_voids_records_and_keeps_original_files(self):
        rows=self.approve();cert=self.certificate()
        from django.core.files.base import ContentFile
        cert.pdf.save('original.pdf',ContentFile(b'original signed PDF'),save=True)
        original=Path(cert.pdf.path);before=original.read_bytes()
        self.batch.status='issued';self.batch.save()
        GenerationTask.objects.filter(version=self.version).update(status='done')
        answer=withdraw_approval(rows[0].pk,self.admin_a,'发现获奖信息错误')
        self.assertEqual(answer['voided_certificates'],1)
        cert.refresh_from_db();self.assertEqual(cert.status,'void');self.assertEqual(original.read_bytes(),before)
        self.assertEqual(GenerationTask.objects.get(version=self.version).status,'done')
        result=self.client_as().post('/api/v1/verification/query/',{'number':cert.number},format='json')
        self.assertEqual(result.data['status'],'void')
        self.assertTrue(AuditEvent.objects.filter(action='approval.withdrawn').exists())
        from .prepared import request_file
        archive=request_file(self.admin_a,'batch_zip',batch_id=self.batch.pk)
        self.assertEqual(archive.version_id,self.version.pk)

    def test_other_department_cannot_withdraw_approval(self):
        rows=self.approve(False)
        answer=self.client_as(self.admin_b).post(f'/api/v1/approvals/{rows[0].pk}/withdraw/',{'reason':'更正'},format='json')
        self.assertIn(answer.status_code,[403,404])
        self.assertEqual(ApprovalDecision.objects.get(requirement=rows[0]).decision,'approved')

    def test_cancelled_worker_does_not_mark_new_revision_failed(self):
        rows=self.approve();task=GenerationTask.objects.get(version=self.version)
        import uuid
        task.status='running';task.lease_token=uuid.uuid4();task.save()
        def cancelled(*args):
            withdraw_approval(rows[0].pk,self.admin_a,'误操作')
            raise RuntimeError('租约已失效')
        with patch('awards.prepared.claim_file',return_value=None),patch('awards.management.commands.runworker.claim_task',return_value=task),patch('awards.management.commands.runworker.process_task',side_effect=cancelled):
            call_command('runworker',once=True,stdout=io.StringIO())
        self.batch.refresh_from_db();self.assertEqual(self.batch.status,'returned')
        self.assertFalse(AuditEvent.objects.filter(action='generation.failed').exists())

    def test_submission_reuses_validated_renderer_for_ready_preview(self):
        self.version.snapshot={'template':{'engine':'pptist','page':{'width':842,'height':595}}};self.version.save()
        fake=Mock();fake.preflight.return_value=[]
        def render(template,seals,values,output):
            from reportlab.pdfgen.canvas import Canvas
            canvas=Canvas(output,pagesize=(842,595));canvas.drawString(50,400,'PREVIEW');canvas.save()
        fake.render.side_effect=render
        with patch('awards.ppt_renderer.renderer',return_value=fake),self.captureOnCommitCallbacks(execute=True):
            submit_batch(self.batch.pk,self.owner)
        assets=list(PreparedFile.objects.filter(version=self.version))
        self.assertEqual({item.kind for item in assets},{'batch_preview','batch_thumbnail'})
        self.assertTrue(all(item.status=='ready' and item.file.storage.exists(item.file.name) for item in assets))
        self.assertEqual(fake.preflight.call_count,1);self.assertEqual(fake.render.call_count,1)

    def test_delivery_keeps_latest_canvas_and_all_historical_versions(self):
        old=self.version.template_version.template
        latest=Template.objects.create(name='最新编辑模板',department=self.departments[0],created_by=self.superuser)
        canvas={'title':'应保留的模板'}
        version=TemplateVersion.objects.create(template=latest,number=1,canvas=canvas)
        out=io.StringIO();call_command('prepare_delivery',apply=True,stdout=out)
        self.assertEqual(json.loads(out.getvalue())['kept_template'],latest.pk)
        latest.refresh_from_db();old.refresh_from_db();version.refresh_from_db()
        self.assertEqual(latest.name,'标准模板');self.assertTrue(latest.published);self.assertIsNotNone(old.deleted_at)
        self.assertEqual(version.canvas,canvas);self.assertTrue(TemplateVersion.objects.filter(pk=self.version.template_version_id).exists())


class VerificationConcurrencyTests(TransactionTestCase):
    def test_postgresql_concurrent_requests_cannot_exceed_sixty(self):
        if connection.vendor!='postgresql':self.skipTest('PostgreSQL lock regression')
        VerificationRateLimit.objects.create(ip_address='127.0.0.77')
        def reserve(_):
            close_old_connections()
            try:return reserve_query('127.0.0.77')
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=5) as pool:results=list(pool.map(reserve,range(70)))
        self.assertEqual(results.count(0),60)
        self.assertEqual(len([item for item in results if item>0]),10)
