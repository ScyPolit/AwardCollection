"""Retain the latest selectable template while preserving every historical canvas."""
import json
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.utils import timezone
from awards.models import Template, AuditEvent


class Command(BaseCommand):
    help = 'Inspect or apply the authorized final template selection'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--keep-template', type=int)

    @transaction.atomic
    def handle(self, *args, **options):
        available = Template.objects.filter(deleted_at__isnull=True)
        chosen = available.filter(pk=options['keep_template']).first() if options['keep_template'] else available.annotate(last_canvas=models.Max('versions__created_at')).order_by('-last_canvas', '-pk').first()
        if chosen is None or not chosen.versions.exists():
            raise CommandError('没有可保留的有效模板')
        list(Template.objects.select_for_update().filter(deleted_at__isnull=True).values_list('pk', flat=True))
        others = list(available.exclude(pk=chosen.pk).values_list('pk', flat=True))
        version = chosen.versions.order_by('-number').first()
        if options['apply']:
            now = timezone.now()
            Template.objects.filter(pk__in=others).update(deleted_at=now, published=False, updated_at=now)
            Template.objects.filter(pk=chosen.pk).update(name='标准模板', published=True, updated_at=now)
            AuditEvent.objects.create(action='delivery.template_selected', object_type='Template', object_id=str(chosen.pk), detail={'kept_version': version.pk, 'archived_templates': others, 'historical_versions_preserved': True})
        self.stdout.write(json.dumps({'applied': options['apply'], 'kept_template': chosen.pk, 'kept_version': version.pk, 'archived_templates': others, 'historical_versions_preserved': True}))
