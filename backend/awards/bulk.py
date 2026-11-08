"""Atomic batch actions reuse the same scopes and checks as individual actions."""
import re
from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from .models import AuditEvent, CertificateFont
from .management_api import archive, delete_account


@api_view(['POST'])
@transaction.atomic
def bulk_action(request):
    from . import views
    resource, operation = request.data.get('resource'), request.data.get('operation')
    classes = {'departments': views.DepartmentViewSet, 'competitions': views.CompetitionViewSet,
               'batches': views.BatchViewSet, 'templates': views.TemplateViewSet, 'seals': views.SealViewSet,
               'certificates': views.CertificateViewSet, 'notifications': views.NotificationViewSet}
    if resource not in {*classes, 'accounts', 'fonts'}:
        raise ValidationError('此类记录不支持批量修改；审批和审计记录需要保留')
    ids = request.data.get('ids')
    if not isinstance(ids, list) or not 1 <= len(ids) <= 200:
        raise ValidationError('请选择1～200条记录')
    if resource == 'fonts':
        if any(not isinstance(pk, str) or not re.fullmatch(r'[0-9a-f]{64}', pk) for pk in ids):
            raise ValidationError('内置字体不能删除，请只选择导入字体')
    elif any(not isinstance(pk, int) or isinstance(pk, bool) or pk <= 0 for pk in ids):
        raise ValidationError('所选记录编号无效')
    ids = sorted(set(ids))
    if operation not in ('delete', 'enable', 'disable'):
        raise ValidationError('批量操作无效')
    if operation != 'delete' and resource not in ('competitions', 'seals', 'templates'):
        raise ValidationError('此类记录不支持批量切换状态')
    if resource == 'accounts':
        items = list(get_user_model().objects.select_for_update(of=("self",)).filter(pk__in=ids, management_profile__deleted_at__isnull=True).order_by('pk'))
        if len(items) != len(ids):
            raise PermissionDenied('所选记录已删除或无权操作，请刷新后重选')
        for item in items:
            delete_account(request.user, item)
    elif resource == 'fonts':
        if not request.user.is_superuser:
            raise PermissionDenied('只有超级管理员可以删除字体')
        items = list(CertificateFont.objects.select_for_update().filter(pk__in=ids, deleted_at__isnull=True).order_by('pk'))
        if len(items) != len(ids):
            raise ValidationError('所选字体已删除或不存在')
        for item in items:
            archive(request.user, item)
    else:
        view = classes[resource]()
        view.request, view.args, view.kwargs, view.format_kwarg = request, (), {}, None
        view.action = 'destroy' if operation == 'delete' else 'partial_update'
        queryset = view.get_queryset()
        permitted = set(queryset.filter(pk__in=ids).values_list('pk', flat=True))
        if permitted != set(ids):
            raise PermissionDenied('所选记录已删除或无权操作，请刷新后重选')
        # Lock only the base table: the visibility query may contain DISTINCT,
        # outer joins or annotations, which PostgreSQL cannot lock directly.
        items = list(queryset.model.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
        for item in items:
            view.kwargs = {'pk': item.pk}
            if operation == 'delete':
                view.perform_destroy(item)
            else:
                key = 'published' if resource == 'templates' else 'active'
                serializer = view.get_serializer(item, data={key: operation == 'enable'}, partial=True)
                serializer.is_valid(raise_exception=True)
                view.perform_update(serializer)
    AuditEvent.objects.create(actor=request.user, action='management.bulk_'+operation, object_type=resource, object_id='', detail={'ids': ids, 'count': len(ids)})
    return Response({'count': len(ids), 'operation': operation})
