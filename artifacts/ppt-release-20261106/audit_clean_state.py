"""Read-only checks after the explicitly authorized demo cleanup."""
import hashlib
import json
from pathlib import Path
from django.contrib.auth import get_user_model
from awards.models import (
    Template, Competition, AwardBatch, Certificate, GenerationTask,
    Notification, Department, Seal, CertificateFont, CertificateSequence, AuditEvent,
)

template = Template.objects.get(pk=4)
version = template.versions.order_by('-number').first()
digest = hashlib.sha256(json.dumps(version.canvas, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
assert digest == '5a84ce02e79ac548da11fb419f7df420f316969d4a5d2a2b6fc92f6b2e6a9fed'
assert template.name == '标准模板' and template.created_by_id == 1
assert get_user_model().objects.count() == 1 and get_user_model().objects.get(pk=1).is_superuser
counts = {model.__name__: model.objects.count() for model in (Competition, AwardBatch, Certificate, GenerationTask, Notification)}
assert not any(counts.values()), counts
assert Template.objects.count() == 1
assert list(Department.objects.values_list('pk', flat=True)) == [6]
assert list(Seal.objects.values_list('pk', flat=True)) == [7]
seal = Seal.objects.get(pk=7).versions.get(number=1)
assert hashlib.sha256(Path(seal.image.path).read_bytes()).hexdigest() == seal.sha256 == '97e68f7310fa954d3d825020ceecad47555995f0090b5bb6eb18751ca5944ac3'
font_ids = ['79ba39fde98703ec0cd804ba1119b915f5e8f4e6663b2d729105b0f4c761ded6', '7f901dfb0526d542740264fb5ba8dfe483293ad060270d273593e2f04a69d080']
for font_id in font_ids:
    font = CertificateFont.objects.get(pk=font_id)
    assert hashlib.sha256(Path(font.file.path).read_bytes()).hexdigest() == font_id
sequences = list(CertificateSequence.objects.values('year', 'next_value'))
assert any(item['year'] == 2026 and item['next_value'] >= 5613 for item in sequences)
assert AuditEvent.objects.filter(action='system.authorized_demo_cleanup').exists()
print('FINAL_AUDIT=' + json.dumps({'accounts': 1, 'templates': 1, 'template_name': template.name, 'template_version': version.number, 'canvas_sha256': digest, 'business_counts': counts, 'formal_seal_unchanged': True, 'formal_fonts_unchanged': True, 'sequence_preserved': sequences, 'audit_retained': True}, ensure_ascii=False))
