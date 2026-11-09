from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from .models import (
    ApprovalDepartment, AwardBatch, Certificate, Competition, Department,
    Notification, RevocationRequest, Seal, SealVersion, TeamAward, Template,
    TemplateVersion,
)


class AccountCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=1024)
    name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    role = serializers.ChoiceField(choices=["admin", "owner"], default="owner")
    department = serializers.PrimaryKeyRelatedField(
        queryset=Department.objects.filter(deleted_at__isnull=True),
        required=False, allow_null=True,
    )

    def to_internal_value(self, data):
        # DRF normally ignores unknown fields, which can hide tampering such as
        # department_id or is_superuser behind an apparently successful create.
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: "不支持的字段" for key in sorted(unknown)})
        return super().to_internal_value(data)

    def validate(self, attrs):
        if attrs["role"] == "admin":
            if not self.context["request"].user.is_superuser:
                raise PermissionDenied("只有超管可以创建部门管理员")
            if not attrs.get("department"):
                raise serializers.ValidationError({"department": "部门管理员需要选择管理部门"})
        elif attrs.get("department") is not None:
            raise serializers.ValidationError({"department": "负责人是全局角色，创建时不能指定部门"})
        User = get_user_model()
        candidate = User(username=attrs["username"], first_name=attrs["name"])
        try:
            User._meta.get_field("username").run_validators(attrs["username"])
            validate_password(attrs["password"], candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError("；".join(exc.messages))
        return attrs


class UserOptionSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()

    class Meta:
        model = get_user_model()
        fields = ["id", "username", "label"]

    def get_label(self, obj):
        return obj.get_full_name() or obj.username


class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ["id", "name", "code"]


class CompetitionSerializer(serializers.ModelSerializer):
    created_by_name = serializers.CharField(source="created_by.username", read_only=True)
    department_names = serializers.SerializerMethodField()
    collaborator_names = serializers.SerializerMethodField()
    departments = serializers.PrimaryKeyRelatedField(many=True, queryset=Department.objects.filter(deleted_at__isnull=True))
    collaborators = serializers.PrimaryKeyRelatedField(many=True, queryset=get_user_model().objects.none(), required=False, allow_empty=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if request := self.context.get("request"):
            from .scopes import collaborator_options
            self.fields["collaborators"].child_relation.queryset = collaborator_options(request.user)

    class Meta:
        model = Competition
        fields = ["id", "name", "award_presets", "active", "created_at", "created_by_name", "departments", "department_names", "collaborators", "collaborator_names"]
        read_only_fields = ["created_at"]

    def get_department_names(self, obj):
        return list(obj.departments.values_list("name", flat=True))

    def get_collaborator_names(self, obj):
        return [user.get_full_name() or user.username for user in obj.collaborators.all()]


class BatchSerializer(serializers.ModelSerializer):
    competition_name = serializers.CharField(source="competition.name", read_only=True)
    team_count = serializers.SerializerMethodField()
    approval_summary = serializers.SerializerMethodField()
    template_version = serializers.PrimaryKeyRelatedField(
        queryset=TemplateVersion.objects.none(),
        write_only=True,
        required=False,
    )
    output_formats = serializers.ListField(
        child=serializers.ChoiceField(choices=["pdf", "png"]),
        write_only=True,
        required=False,
    )
    seal_versions = serializers.DictField(
        child=serializers.IntegerField(min_value=1),
        write_only=True,
        required=False,
    )

    class Meta:
        model = AwardBatch
        fields = [
            "id", "public_id", "name", "status", "current_version", "competition",
            "competition_name", "team_count", "approval_summary", "created_at",
            "template_version", "output_formats", "seal_versions",
        ]
        read_only_fields = ["public_id", "status", "current_version", "created_at"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if request := self.context.get("request"):
            from .prepared import template_versions_for
            self.fields["template_version"].queryset = template_versions_for(request.user)

    def get_team_count(self, obj):
        if hasattr(obj, "team_count_value"):return obj.team_count_value
        version = obj.versions.only("pk").filter(number=obj.current_version).first()
        return getattr(obj, "team_count_value", None) if hasattr(obj, "team_count_value") else (version.awards.count() if version else 0)

    def get_approval_summary(self, obj):
        if hasattr(obj, "required_count_value"):return {"approved":obj.approved_count_value,"total":obj.required_count_value}
        version = obj.versions.only("pk").filter(number=obj.current_version).first()
        if not version:
            return {"approved": 0, "total": 0}
        return {"approved": obj.approved_count_value, "total": obj.required_count_value} if hasattr(obj, "required_count_value") else {"approved": version.required_departments.filter(decision__decision="approved").count(), "total": version.required_departments.count()}

    def validate_output_formats(self, value):
        formats = list(dict.fromkeys(value))
        if not formats:
            raise serializers.ValidationError("至少选择一种发放格式")
        return formats


class AwardSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamAward
        fields = ["source_row", "members", "award_name", "team_name", "work_name", "category", "teachers", "note"]


class ApprovalSerializer(serializers.ModelSerializer):
    batch_id = serializers.IntegerField(source="version.batch_id", read_only=True)
    batch_name = serializers.CharField(source="version.batch.name", read_only=True)
    version_number = serializers.IntegerField(source="version.number", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    competition_name = serializers.CharField(source="version.batch.competition.name", read_only=True)
    decision = serializers.SerializerMethodField()
    decision_detail = serializers.SerializerMethodField()
    can_review = serializers.SerializerMethodField()
    can_withdraw = serializers.SerializerMethodField()
    seal_version = serializers.SerializerMethodField()
    seal_label = serializers.SerializerMethodField()
    seal_selected = serializers.SerializerMethodField()

    class Meta:
        model = ApprovalDepartment
        fields = ["id", "batch_id", "batch_name", "version_number", "department", "department_name", "competition_name", "decision", "decision_detail", "created_at", "can_review", "can_withdraw", "seal_version", "seal_label", "seal_selected"]

    def get_can_withdraw(self, obj):
        request = self.context.get('request')
        if not request or self.get_decision(obj) != 'approved':
            return False
        if request.user.is_superuser:
            return True
        from .scopes import managed_departments
        if '_approval_departments' not in self.context:
            self.context['_approval_departments'] = set(managed_departments(request.user))
        return obj.department_id in self.context['_approval_departments']

    def get_can_review(self, obj):
        request = self.context.get("request")
        if not request or obj.version.batch.status != "review" or obj.version.number != obj.version.batch.current_version:
            return False
        if request.user.is_superuser:
            return True
        from .scopes import managed_departments
        if '_approval_departments' not in self.context:
            self.context['_approval_departments'] = set(managed_departments(request.user))
        return obj.department_id in self.context['_approval_departments']

    def get_seal_version(self, obj):
        return obj.seal_version_id if self.get_can_review(obj) else None

    def get_seal_label(self, obj):
        if not obj.seal_version_id:
            return "待部门管理员选择"
        if not self.get_can_review(obj):
            return "已确认用章"
        return f"{obj.seal_version.seal.name} · v{obj.seal_version.number}"

    def get_seal_selected(self, obj):
        return obj.seal_version_id is not None

    def get_decision(self, obj):
        return getattr(getattr(obj, "decision", None), "decision", None)

    def get_decision_detail(self, obj):
        decision = getattr(obj, "decision", None)
        if not decision:
            return None
        return {"actor": decision.actor.username, "comment": decision.comment, "issue_rows": decision.issue_rows, "created_at": decision.created_at, 'withdrawn_at':decision.withdrawn_at, 'withdrawal_reason':decision.withdrawal_reason, 'withdrawn_by':decision.withdrawn_by_id}


class TemplateVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateVersion
        fields = ["id", "number", "canvas", "summary", "created_at"]


class TemplateSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    latest_version = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()
    is_mine = serializers.SerializerMethodField()

    class Meta:
        model = Template
        fields = ["id", "name", "department", "department_name", "source", "published", "scope", "is_mine", "latest_version", "created_at", "can_edit", "can_manage"]
        read_only_fields = ["source", "scope", "created_at"]

    def get_is_mine(self, obj):
        request = self.context.get("request")
        return bool(request and obj.created_by_id == request.user.pk)

    def get_can_manage(self, obj):
        request = self.context.get('request')
        if not request:
            return False
        from .permissions import can_manage_template
        return can_manage_template(request.user, obj)

    def get_can_edit(self, obj):
        return self.get_can_manage(obj)

    def get_latest_version(self, obj):
        if hasattr(obj, "light_versions"):
            version = obj.light_versions[0] if obj.light_versions else None
            return {"id": version.pk, "number": version.number, "summary": version.summary, "created_at": version.created_at} if version else None
        version = obj.versions.order_by("-number").first()
        return TemplateVersionSerializer(version).data if version else None


class SealVersionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SealVersion
        fields = ["id", "number", "sha256", "created_at"]


class SealSerializer(serializers.ModelSerializer):
    department_name = serializers.CharField(source="department.name", read_only=True)
    versions = SealVersionSerializer(many=True, read_only=True)

    class Meta:
        model = Seal
        fields = ["id", "name", "department", "department_name", "active", "versions", "created_at"]


class CertificateSerializer(serializers.ModelSerializer):
    batch_id = serializers.IntegerField(source="award.version.batch_id", read_only=True)
    competition_name = serializers.SerializerMethodField()

    def get_competition_name(self,obj):
        return getattr(obj, "frozen_competition_name", None) or obj.award.version.batch.competition.name
    batch_name = serializers.CharField(source="award.version.batch.name", read_only=True)
    team_name = serializers.CharField(source="award.team_name", read_only=True)
    award_name = serializers.CharField(source="award.award_name", read_only=True)

    class Meta:
        model = Certificate
        fields = ["id", "number", "status", "published_at", "created_at", "competition_name", "batch_id", "batch_name", "team_name", "award_name", "notes"]
        read_only_fields = ["number", "status", "published_at", "created_at"]


class RevocationSerializer(serializers.ModelSerializer):
    certificate_number = serializers.CharField(source="certificate.number", read_only=True)
    approved_departments = serializers.SerializerMethodField()
    total_departments = serializers.SerializerMethodField()
    approval_departments = serializers.SerializerMethodField()

    class Meta:
        model = RevocationRequest
        fields = ["id", "certificate", "certificate_number", "reason", "status", "approved_departments", "total_departments", "created_at", "approval_departments"]

    def get_approval_departments(self, obj):
        from .permissions import is_department_admin
        request = self.context.get('request')
        return [{"id": r.department_id, "name": r.department.name} for r in obj.certificate.award.version.required_departments.select_related('department') if request and is_department_admin(request.user, r.department)]

    def get_approved_departments(self, obj):
        return obj.decisions.filter(decision="approved").count()

    def get_total_departments(self, obj):
        return obj.certificate.award.version.required_departments.count()


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
        read_only_fields = ["user", "title", "body", "target", "kind", "created_at", "updated_at"]
