from rest_framework import serializers
from .models import AwardBatch, Certificate, Competition, Notification, Seal, TeamAward, Template


class CompetitionSerializer(serializers.ModelSerializer):
    departments = serializers.PrimaryKeyRelatedField(many=True, queryset=Competition._meta.get_field("departments").remote_field.model.objects.all(), required=False, allow_empty=True)
    collaborators = serializers.PrimaryKeyRelatedField(many=True, queryset=Competition._meta.get_field("collaborators").remote_field.model.objects.all(), required=False, allow_empty=True)

    class Meta:
        model = Competition
        fields = ["id", "name", "award_presets", "active", "created_at", "departments", "collaborators"]
        read_only_fields = ["created_at"]


class BatchSerializer(serializers.ModelSerializer):
    competition_name = serializers.CharField(source="competition.name", read_only=True)
    class Meta:
        model = AwardBatch
        fields = ["id", "public_id", "name", "status", "current_version", "competition", "competition_name", "created_at"]


class AwardSerializer(serializers.ModelSerializer):
    class Meta:
        model = TeamAward
        fields = "__all__"


class TemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Template
        fields = "__all__"


class SealSerializer(serializers.ModelSerializer):
    class Meta:
        model = Seal
        fields = "__all__"


class CertificateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Certificate
        fields = ["id", "number", "status", "published_at", "created_at"]


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = "__all__"
