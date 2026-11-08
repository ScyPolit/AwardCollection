import hashlib
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from . import tests as fixtures
from .models import ApprovalDepartment, ApprovalDecision, AwardBatch, BatchVersion, Certificate, Competition, DepartmentMembership, GenerationTask, SealVersion, TeamAward
from .services import submit_batch, decide, choose_approval_seal
from .integrity import verify
from .prepared import key_for, request_file
from .realtime import snapshot_for


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ApprovalArchiveBulkTests(TestCase):
    def setUp(self):
        fixtures.WorkflowTests.setUp(self)
        self.client = APIClient()
        self.client.force_authenticate(self.owner)
        self.requirements = list(self.version.required_departments.order_by('department_id'))
        self.seal_ids = {r.department_id: r.seal_version_id for r in self.requirements}

    def pending(self):
        self.version.required_departments.update(seal_version=None)
        submit_batch(self.batch.pk, self.owner)

    def create_payload(self, **extra):
        return {'name': '新流程测试批次', 'competition': self.batch.competition_id,
                'template_version': self.version.template_version_id, **extra}

    def alternate_seal(self, requirement):
        return SealVersion.objects.create(seal=requirement.seal_version.seal, number=2,
                                         image=ContentFile(b'alternate', name='alt.png'), sha256=hashlib.sha256(b'alternate').hexdigest())

    def bulk(self, resource, ids, operation='delete'):
        return self.client.post('/api/v1/management/bulk/', {'resource': resource, 'operation': operation, 'ids': ids}, format='json')

    def certificate(self, version=None, index=1):
        version = version or self.version
        award = self.award if version.pk == self.version.pk and index == 1 else TeamAward.objects.create(version=version, source_row=index+10, members=['测试成员'], award_name='一等奖')
        return Certificate.objects.create(award=award, number=f'BULK-TEST-{version.pk}-{index}', published_at=timezone.now())

    def test_owner_creates_pending_departments_without_seal_access(self):
        response = self.client.post('/api/v1/batches/', self.create_payload(), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        version = BatchVersion.objects.get(batch_id=response.data['id'], number=1)
        self.assertEqual(version.required_departments.count(), 2)
        self.assertFalse(version.required_departments.filter(seal_version__isnull=False).exists())

    def test_owner_cannot_supply_seal_version(self):
        response = self.client.post('/api/v1/batches/', self.create_payload(seal_versions={str(self.departments[0].pk): self.seal_ids[self.departments[0].pk]}), format='json')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(AwardBatch.objects.count(), 1)

    def test_admin_can_prefill_only_own_department(self):
        self.client.force_authenticate(self.admin_a)
        foreign = {str(self.departments[1].pk): self.seal_ids[self.departments[1].pk]}
        self.assertEqual(self.client.post('/api/v1/batches/', self.create_payload(seal_versions=foreign), format='json').status_code, 403)
        own = {str(self.departments[0].pk): self.seal_ids[self.departments[0].pk]}
        response = self.client.post('/api/v1/batches/', self.create_payload(seal_versions=own), format='json')
        self.assertEqual(response.status_code, 201, response.data)
        version = BatchVersion.objects.get(batch_id=response.data['id'], number=1)
        self.assertEqual(version.required_departments.get(department=self.departments[0]).seal_version_id, own[str(self.departments[0].pk)])
        self.assertIsNone(version.required_departments.get(department=self.departments[1]).seal_version_id)

    def test_pending_submission_has_valid_integrity(self):
        self.pending(); self.version.refresh_from_db(); verify(self.version)
        self.assertEqual(snapshot_for(self.admin_a.pk)['pending'], 1)

    def test_approval_requires_a_chosen_seal(self):
        self.pending(); self.client.force_authenticate(self.admin_a)
        response = self.client.post(f'/api/v1/approvals/{self.requirements[0].pk}/decide/', {'decision': 'approved'}, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertFalse(ApprovalDecision.objects.exists())

    def test_selecting_seal_is_delegated_and_reseals_only_verified_data(self):
        self.pending()
        row = self.requirements[0]
        choose_approval_seal(row.pk, self.admin_a, self.seal_ids[row.department_id], None)
        self.version.refresh_from_db(); verify(self.version)
        row.refresh_from_db(); self.assertEqual(row.seal_version_id, self.seal_ids[row.department_id])
        self.assertIsNone(self.version.required_departments.get(department=self.departments[1]).seal_version_id)

    def test_cross_department_and_owner_seal_changes_rejected(self):
        self.pending(); row = self.requirements[0]
        with self.assertRaises(PermissionError):
            choose_approval_seal(row.pk, self.owner, self.seal_ids[row.department_id])
        with self.assertRaises(PermissionError):
            choose_approval_seal(row.pk, self.admin_b, self.seal_ids[row.department_id])
        with self.assertRaises(ValueError):
            choose_approval_seal(row.pk, self.admin_a, self.seal_ids[self.departments[1].pk])

    def test_tampering_cannot_be_legitimized_by_choosing_a_seal(self):
        self.pending(); self.award.award_name = '数据库篡改'; self.award.save()
        with self.assertRaisesMessage(ValueError, '完整性'):
            choose_approval_seal(self.requirements[0].pk, self.admin_a, self.seal_ids[self.departments[0].pk])

    def test_stale_seal_choice_is_rejected(self):
        submit_batch(self.batch.pk, self.owner)
        alt = self.alternate_seal(self.requirements[0])
        with self.assertRaisesMessage(ValueError, '其他管理员'):
            choose_approval_seal(self.requirements[0].pk, self.admin_a, alt.pk, None)

    def test_missing_seal_file_returns_actionable_error_and_rolls_back(self):
        self.pending()
        row = self.requirements[0]
        row.seal_version.image.delete(save=False)
        with self.assertRaisesMessage(ValueError, '公章文件不存在'):
            choose_approval_seal(row.pk, self.admin_a, self.seal_ids[row.department_id], None)
        row.refresh_from_db(); self.assertIsNone(row.seal_version_id)
        self.version.refresh_from_db(); verify(self.version)

    def test_approved_department_cannot_change_its_seal(self):
        submit_batch(self.batch.pk, self.owner)
        row = self.requirements[0]; alt = self.alternate_seal(row)
        decide(row.pk, self.admin_a, 'approved')
        with self.assertRaisesMessage(ValueError, '已审批'):
            choose_approval_seal(row.pk, self.superuser, alt.pk)
        row.refresh_from_db(); self.assertNotEqual(row.seal_version_id, alt.pk)

    def test_new_workflow_queues_only_after_all_departments_choose_and_approve(self):
        self.pending()
        for row, actor in zip(self.requirements, (self.admin_a, self.admin_b)):
            decide(row.pk, actor, 'approved', '核对无误', seal_version_id=self.seal_ids[row.department_id], expected_seal_version=None)
        self.assertEqual(GenerationTask.objects.filter(version=self.version).count(), 1)
        self.batch.refresh_from_db(); self.assertEqual(self.batch.status, 'queued')
        self.version.refresh_from_db(); verify(self.version)

    def test_return_without_seal_and_problem_row_annotations(self):
        self.pending()
        decide(self.requirements[0].pk, self.admin_a, 'returned', '请更正第2行', issue_rows=[2])
        self.assertEqual(ApprovalDecision.objects.get().issue_rows, [2])
        self.batch.refresh_from_db(); self.assertEqual(self.batch.status, 'returned')

    def test_admin_editor_and_super_submitter_can_approve_and_see_pending(self):
        self.award.last_edited_by = self.admin_a; self.award.save()
        submit_batch(self.batch.pk, self.admin_a)
        self.assertEqual(snapshot_for(self.admin_a.pk)['pending'], 1)
        self.assertIsNone(decide(self.requirements[0].pk, self.admin_a, 'approved'))
        self.assertIsNotNone(decide(self.requirements[1].pk, self.superuser, 'approved'))

    def test_seal_choice_invalidates_prepared_preview(self):
        self.pending()
        before = key_for('batch_thumbnail', self.version.pk)
        choose_approval_seal(self.requirements[0].pk, self.admin_a, self.seal_ids[self.departments[0].pk], None)
        self.assertNotEqual(before, key_for('batch_thumbnail', self.version.pk))
        self.assertEqual(request_file(self.admin_a, 'batch_thumbnail', batch_id=self.batch.pk).kind, 'batch_thumbnail')

    def test_partial_approval_and_seal_choice_update_other_departments_live_revision(self):
        self.pending()
        before = snapshot_for(self.admin_b.pk)['revision']
        choose_approval_seal(self.requirements[0].pk, self.admin_a, self.seal_ids[self.departments[0].pk], None)
        selected = snapshot_for(self.admin_b.pk)['revision']
        self.assertNotEqual(before, selected)
        decide(self.requirements[0].pk, self.admin_a, 'approved')
        self.assertNotEqual(selected, snapshot_for(self.admin_b.pk)['revision'])

    def test_approval_details_expose_own_selection_only(self):
        submit_batch(self.batch.pk, self.owner)
        self.client.force_authenticate(self.admin_a)
        response = self.client.get(f'/api/v1/batches/{self.batch.pk}/detail/')
        rows = response.data['approvals']
        self.assertTrue(rows[0]['can_review']); self.assertIsNotNone(rows[0]['seal_version'])
        self.assertFalse(rows[1]['can_review']); self.assertIsNone(rows[1]['seal_version'])

    def test_bulk_approvals_are_atomic_on_invalid_department_seal(self):
        self.pending(); self.client.force_authenticate(self.superuser)
        items = [{'id': row.pk, 'seal_version': self.seal_ids[self.departments[0].pk], 'expected_seal_version': None} for row in self.requirements]
        response = self.client.post('/api/v1/approvals/bulk-decide/', {'decision': 'approved', 'items': items}, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertFalse(ApprovalDecision.objects.exists())
        self.assertFalse(self.version.required_departments.filter(seal_version__isnull=False).exists())
        self.version.refresh_from_db(); verify(self.version)

    def test_bulk_return_merges_same_batch(self):
        self.pending(); self.client.force_authenticate(self.superuser)
        response = self.client.post('/api/v1/approvals/bulk-decide/', {'decision': 'returned', 'comment': '整批更正', 'items': [{'id': r.pk} for r in self.requirements]}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)

    def test_certificate_tree_and_children_stay_scoped_and_paginated(self):
        self.certificate(); self.certificate(index=2)
        other = BatchVersion.objects.create(batch=self.batch, number=2, template_version=self.version.template_version)
        ApprovalDepartment.objects.create(version=other, department=self.departments[1], seal_version_id=self.seal_ids[self.departments[1].pk])
        self.certificate(other)
        self.client.force_authenticate(self.admin_a)
        tree = self.client.get('/api/v1/certificates/batches/').data
        self.assertEqual(tree['count'], 1); self.assertEqual(tree['results'][0]['certificate_count'], 2)
        response = self.client.get(f'/api/v1/certificates/?batch={self.batch.pk}&page_size=1')
        self.assertEqual(response.data['count'], 2); self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['batch_id'], self.batch.pk)

    def test_certificate_tree_searches_batch_name(self):
        self.certificate()
        self.assertEqual(self.client.get('/api/v1/certificates/batches/', {'search': '测试批次'}).data['count'], 1)
        self.assertEqual(self.client.get('/api/v1/certificates/batches/', {'search': '不存在'}).data['count'], 0)

    def test_bulk_delete_rolls_back_when_one_record_is_outside_scope(self):
        other = Competition.objects.create(name='他人竞赛', created_by=self.outsider)
        response = self.bulk('competitions', [self.batch.competition_id, other.pk])
        self.assertEqual(response.status_code, 403)
        self.batch.competition.refresh_from_db(); self.assertIsNone(self.batch.competition.deleted_at)

    def test_bulk_delete_running_batch_rolls_back_other_deletes(self):
        other = AwardBatch.objects.create(name='运行批次', competition=self.batch.competition, created_by=self.owner, status='queued')
        self.assertEqual(self.bulk('batches', [self.batch.pk, other.pk]).status_code, 400)
        self.batch.refresh_from_db(); self.assertIsNone(self.batch.deleted_at)

    def test_bulk_delete_accounts_cannot_delete_current_user(self):
        self.client.force_authenticate(self.superuser)
        response = self.bulk('accounts', [self.owner.pk, self.superuser.pk])
        self.assertEqual(response.status_code, 403)
        self.owner.refresh_from_db(); self.assertTrue(self.owner.is_active)

    def test_bulk_certificate_delete_is_archival_and_owner_cannot_do_it(self):
        certificate = self.certificate()
        self.assertEqual(self.bulk('certificates', [certificate.pk]).status_code, 403)
        self.client.force_authenticate(self.admin_a)
        self.assertEqual(self.bulk('certificates', [certificate.pk]).status_code, 200)
        certificate.refresh_from_db(); self.assertIsNotNone(certificate.deleted_at)
        self.assertEqual(self.client.get('/api/v1/certificates/batches/').data['count'], 0)

    def test_bulk_actions_reject_invalid_ids_and_immutable_logs(self):
        for ids in ([], [True], [0], list(range(1, 202))):
            self.assertEqual(self.bulk('batches', ids).status_code, 400)
        self.assertEqual(self.bulk('logs', [1]).status_code, 400)
        self.assertEqual(self.bulk('fonts', ['hei']).status_code, 400)

    def test_bulk_roster_delete_creates_one_revision(self):
        TeamAward.objects.create(version=self.version, source_row=3, members=['测试'], award_name='二等奖')
        response = self.client.post(f'/api/v1/batches/{self.batch.pk}/rows/', {'operation': 'bulk_delete', 'source_rows': [2, 3], 'expected_version': 1}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.batch.refresh_from_db(); self.assertEqual(self.batch.current_version, 2)
        self.assertEqual(self.version.awards.count(), 2)
        self.assertEqual(self.batch.versions.get(number=2).awards.count(), 0)
