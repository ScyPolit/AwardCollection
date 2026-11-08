"""Number lookup, configurable disclosures and a database-backed sliding window."""
import math
import re
import time
from django.db import transaction
from rest_framework.exceptions import ValidationError
from .models import Certificate, SystemSetting, VerificationRateLimit, TemplateVersion

DEFAULT_CONFIG = {
    'show_competition': True, 'show_award': True, 'show_team': True,
    'show_members': True, 'mask_members': True, 'show_work': False,
    'show_category': False, 'show_teachers': False, 'mask_teachers': True,
    'show_issue_date': False, 'show_departments': False,
    'show_published_at': False, 'show_batch': False, 'show_template': False,
    'watermark_text': '仅供证书信息核验使用',
}


def configuration():
    setting = SystemSetting.objects.filter(key='public_verification').first()
    return {**DEFAULT_CONFIG, **(setting.value if setting else {})}


def validate_configuration(data):
    if set(data) - DEFAULT_CONFIG.keys():
        raise ValidationError('包含不支持的查验设置')
    result = configuration()
    for key, value in data.items():
        if key == 'watermark_text':
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 160:
                raise ValidationError('水印内容需要1～160个字符')
            result[key] = value.strip()
        else:
            if not isinstance(value, bool):
                raise ValidationError('显示选项必须为布尔值')
            result[key] = value
    return result


def normalize_number(value):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= 40:
        raise ValidationError('请输入有效的证书编号')
    value = value.strip().upper()
    if not re.fullmatch(r'[A-Z0-9-]{1,40}', value):
        raise ValidationError('证书编号只能包含字母、数字及历史编号分隔符')
    return value.replace('-', '')


def find_certificate(value):
    normalized = normalize_number(value)
    candidates = {normalized, value.strip().upper()}
    match = re.fullmatch(r'(\d{4})AC(\d{8,})', normalized)
    if match:
        candidates.add(f'{match[1]}-AC-{match[2]}')
    return Certificate.objects.select_related('award__version__batch__competition').filter(
        number__in=candidates, published_at__isnull=False, deleted_at__isnull=True,
    ).order_by('pk').first()


@transaction.atomic
def reserve_query(ip):
    """Serialize all public/internal query attempts for an IP, across API workers."""
    VerificationRateLimit.objects.get_or_create(ip_address=ip)
    bucket = VerificationRateLimit.objects.select_for_update().get(pk=ip)
    now = time.time()
    recent = [stamp for stamp in bucket.timestamps if stamp > now - 60]
    if len(recent) >= 60:
        return max(1, math.ceil(recent[0] + 60 - now))
    bucket.timestamps = recent + [now]
    bucket.save(update_fields=['timestamps', 'updated_at'])
    return 0


def mask_names(names, mask):
    return [name[:1] + '*' * max(1, len(name) - 1) for name in names] if mask else names


def result(certificate, *, internal=False):
    config = configuration()
    answer = {'found': certificate is not None, 'watermark_text': config['watermark_text']}
    if certificate is None:
        return answer
    award = certificate.award
    version = award.version
    snapshot = version.snapshot
    answer.update(number=certificate.number, status=certificate.status)
    fields = {
        'competition': ('show_competition', snapshot.get('competition', {}).get('name', version.batch.competition.name)),
        'award': ('show_award', award.award_name), 'team': ('show_team', award.team_name),
        'work': ('show_work', award.work_name), 'category': ('show_category', award.category),
        'issue_date': ('show_issue_date', snapshot.get('issue_date', '')),
        'published_at': ('show_published_at', certificate.published_at),
        'batch': ('show_batch', version.batch.name),
        'template': ('show_template', ''),
    }
    for name, (option, value) in fields.items():
        if internal or config[option]:
            if name == 'template':
                value = TemplateVersion.objects.filter(pk=version.template_version_id).values_list('template__name', flat=True).first() or ''
            answer[name] = value
    if internal or config['show_members']:
        answer['members'] = mask_names(award.members, config['mask_members'] and not internal)
    if internal or config['show_teachers']:
        answer['teachers'] = mask_names(award.teachers, config['mask_teachers'] and not internal)
    if internal or config['show_departments']:
        answer['departments'] = [item['name'] for item in snapshot.get('department_details', [])]
    return answer
