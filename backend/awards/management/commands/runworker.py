"""Bounded generation and disk preparation worker. Only a small window is in flight."""
import multiprocessing
import os
import shutil
import time
from pathlib import Path
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth import get_user_model
from django.utils import timezone
from awards.models import AwardBatch, Certificate, DepartmentMembership, GenerationTask, Notification, AuditEvent
from awards.renderer import render_certificate_payload, image_from_pdf
from awards.services import allocate_number, claim_task
from awards.fonts import font_file

from awards.render_jobs import init_render_process, render_job, close_render_process


def render_concurrency(template):
    requested = max(1, min(int(os.getenv('RENDER_CONCURRENCY', '1')), 4))
    try:
        limit = int(Path('/sys/fs/cgroup/memory.max').read_text())
        requested = min(requested, max(1, (limit - 400*1024**2) // (400*1024**2)))
    except (OSError, ValueError):
        pass
    return min(requested, 2) if template.get('engine') == 'pptist' else requested


def process_task(task):
    from awards.integrity import verify, file_digest
    verify(task.version)
    token = task.lease_token
    requirements = list(task.version.required_departments.select_related('department', 'seal_version__seal').order_by('department_id'))
    for item in requirements:
        if not item.seal_version.seal.active:
            raise RuntimeError(f'{item.department.name} 的选定公章已停用')
    snapshot = task.version.snapshot
    names = {item['id']: item['name'] for item in snapshot.get('department_details', [])}
    departments = [{'id': item.department_id, 'name': names.get(item.department_id, item.department.name)} for item in requirements]
    seals = [{'department_id': item.department_id, 'seal_version_id': item.seal_version_id, 'image': item.seal_version.image.path} for item in requirements]
    template = snapshot.get('template') or task.version.template_version.canvas
    font_ids = {'hei'} | {layer.get('fontFamily') or 'hei' for layer in template.get('layers', []) if layer.get('type') == 'text'}
    if template.get('engine') == 'pptist':
        from awards.presentation import presentation_fonts
        font_ids |= presentation_fonts(template)
    fonts = {key: str(font_file(key)) for key in font_ids}
    make_image = 'png' in task.version.output_formats
    attempt = Path(settings.MEDIA_ROOT) / 'temporary' / 'generation' / str(task.pk) / str(token)
    attempt.mkdir(parents=True, exist_ok=True)
    certs = Certificate.objects.filter(award__version_id=task.version_id).exclude(pdf='')
    if make_image:
        certs = certs.exclude(image='')
    processed = certs.count()
    final_root = Path(settings.MEDIA_ROOT) / 'protected' / 'certificates' / str(timezone.localdate().year)
    final_root.mkdir(parents=True, exist_ok=True)

    def jobs():
        for award in task.version.awards.order_by('source_row').iterator(chunk_size=16):
            with transaction.atomic():
                certificate = Certificate.objects.select_for_update().filter(award=award).first()
                if certificate is None:
                    certificate = Certificate.objects.create(award=award, number=allocate_number())
            existing_pdf = None
            if certificate.pdf:
                if not certificate.pdf.storage.exists(certificate.pdf.name) or file_digest(certificate.pdf.path) != certificate.pdf_sha256:
                    raise RuntimeError('已生成 PDF 缺失或被修改，请恢复原件后重试')
                if not make_image:
                    continue
                if certificate.image:
                    if not certificate.image.storage.exists(certificate.image.name) or file_digest(certificate.image.path) != certificate.image_sha256:
                        raise RuntimeError('已生成图片缺失或被修改，请恢复原件后重试')
                    continue
                existing_pdf = certificate.pdf.path
            payload = {key: getattr(award, key) for key in ('team_name','members','award_name','work_name','category','teachers')}
            payload.update(competition_name=snapshot.get('competition', {}).get('name', task.version.batch.competition.name), issue_date=snapshot.get('issue_date', ''))
            yield certificate.pk, (payload, certificate.number, str(attempt), make_image, existing_pdf)

    iterator = iter(jobs())
    concurrency = render_concurrency(template)
    # Template/font data is sent once to each child, never once per queued certificate.
    with ProcessPoolExecutor(max_workers=concurrency, mp_context=multiprocessing.get_context('spawn'), initializer=init_render_process, initargs=(departments, template, seals, fonts, str(settings.MEDIA_ROOT))) as pool:
        in_flight = {}
        exhausted = False
        while in_flight or not exhausted:
            while not exhausted and len(in_flight) < concurrency:
                try:
                    certificate_id, args = next(iterator)
                except StopIteration:
                    exhausted = True
                    break
                in_flight[pool.submit(render_job, *args)] = certificate_id
            if not in_flight:
                break
            done, _ = wait(in_flight, timeout=15, return_when=FIRST_COMPLETED)
            updated = GenerationTask.objects.filter(pk=task.pk, lease_token=token, status='running').update(lease_expires_at=timezone.now()+timedelta(minutes=10))
            if not updated:
                raise RuntimeError('任务租约已失效，旧 worker 停止写入')
            for future in done:
                certificate_id = in_flight.pop(future)
                pdf, image, digest = future.result()
                with transaction.atomic():
                    current = GenerationTask.objects.select_for_update().get(pk=task.pk)
                    if current.lease_token != token or current.status != 'running':
                        raise RuntimeError('任务租约已失效')
                    certificate = Certificate.objects.get(pk=certificate_id)
                    if pdf:
                        dest = final_root / f'{certificate.number}.pdf'
                        os.replace(pdf, dest)
                        certificate.pdf.name = dest.relative_to(settings.MEDIA_ROOT).as_posix()
                    if image:
                        dest = final_root / f'{certificate.number}.png'
                        os.replace(image, dest)
                        certificate.image.name = dest.relative_to(settings.MEDIA_ROOT).as_posix()
                        certificate.image_sha256 = file_digest(dest)
                    certificate.pdf_sha256 = digest
                    certificate.save(update_fields=['pdf','image','pdf_sha256','image_sha256','updated_at'])
                    processed += 1
                    current.processed = processed
                    current.lease_expires_at = timezone.now()+timedelta(minutes=10)
                    current.save(update_fields=['processed','lease_expires_at','updated_at'])
        cleanup = [pool.submit(close_render_process) for _ in range(concurrency)]
        for future in cleanup:
            future.result(timeout=20)
    with transaction.atomic():
        current = GenerationTask.objects.select_for_update().get(pk=task.pk)
        if current.lease_token != token or current.status != 'running':
            raise RuntimeError('任务租约已失效')
        ready = Certificate.objects.filter(award__version_id=task.version_id).exclude(pdf='')
        if make_image:
            ready = ready.exclude(image='')
        if ready.count() != current.total:
            raise RuntimeError('PDF / 图片尚未全部就绪，拒绝发布')
        Certificate.objects.filter(award__version_id=task.version_id, published_at__isnull=True).update(published_at=timezone.now())
        current.processed, current.status, current.error, current.lease_expires_at = current.total, 'done', '', None
        current.save()
        current.version.batch.status = 'issued'
        current.version.batch.save(update_fields=['status','updated_at'])
        competition = current.version.batch.competition
        recipients = set(competition.collaborators.values_list('pk', flat=True)) | {current.version.batch.created_by_id}
        recipients.update(DepartmentMembership.objects.filter(department_id__in=[r.department_id for r in requirements], role='admin', active=True).values_list('user_id', flat=True))
        recipients.update(get_user_model().objects.filter(is_superuser=True, is_active=True).values_list('pk', flat=True))
        AuditEvent.objects.create(action='generation.completed', object_type='AwardBatch', object_id=str(current.version.batch_id), detail={'total': current.total})
        Notification.objects.bulk_create([Notification(user_id=user_id,title='证书签发完成',body=f'批次“{current.version.batch.name}”已完成，服务器正在准备整批 ZIP。',kind='completed',target=f'/business/batches?batch={current.version.batch_id}') for user_id in recipients])
    try:
        from awards.prepared import request_file
        user = get_user_model().objects.filter(pk=current.version.batch.created_by_id).first()
        asset = request_file(user, 'batch_zip', batch_id=current.version.batch_id)
        asset.subscribers.add(*get_user_model().objects.filter(pk__in=recipients, is_active=True))
    except Exception as exc:
        AuditEvent.objects.create(action='archive.queue_failed', object_type='AwardBatch', object_id=str(current.version.batch_id), detail={'error': str(exc)[:500]})
    shutil.rmtree(attempt, ignore_errors=True)
    return current


class Command(BaseCommand):
    help = 'Persistent bounded generation, preview and archive worker'

    def handle(self, *args, **options):
        from awards.prepared import claim_file, process_file
        self.stdout.write('worker started')
        while True:
            file_job = claim_file()
            if file_job:
                process_file(file_job)
                if options['once']:
                    return
                continue
            task = claim_task()
            if task is None:
                if options['once']:
                    return
                time.sleep(2)
                continue
            try:
                process_task(task)
            except Exception as exc:
                Notification.objects.create(user_id=task.version.batch.created_by_id,title='证书生成失败',body='请查看任务错误并重试，已完成的原件保持不变。',kind='failed',target=f'/business/batches?batch={task.version.batch_id}')
                AuditEvent.objects.create(action='generation.failed',object_type='AwardBatch',object_id=str(task.version.batch_id),detail={'error':str(exc)[:1000]})
                AwardBatch.objects.filter(pk=task.version.batch_id,current_version=task.version.number).update(status='failed')
                GenerationTask.objects.filter(pk=task.pk,lease_token=task.lease_token).update(status='failed',error=str(exc)[:1000])
            if options['once']:
                return

    def add_arguments(self, parser):
        parser.add_argument('--once',action='store_true')
