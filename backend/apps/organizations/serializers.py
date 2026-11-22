from django.contrib.auth import get_user_model

from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import Organization, Membership
from .services import create_organization


User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):

    created_by_email = serializers.EmailField(
        source="created_by.email",
        read_only=True
    )

    member_count = serializers.SerializerMethodField()

    class Meta:
        model = Organization

        fields = [
            "id",
            "name",
            "slug",
            "description",
            "is_active",
            "created_by_email",
            "member_count",
            "created_at",
            "updated_at",
        ]

        read_only_fields = [
            "id",
            "is_active",
            "created_by_email",
            "member_count",
            "created_at",
            "updated_at",
        ]

    def get_member_count(self, obj):
        return obj.memberships.filter(
            status=Membership.Status.ACTIVE
        ).count()


class OrganizationCreateSerializer(serializers.ModelSerializer):

    slug = serializers.SlugField(
        validators=[
            UniqueValidator(
                queryset=Organization.objects.all(),
                message="This organization slug is already taken."
            )
        ]
    )

    class Meta:
        model = Organization

        fields = [
            "name",
            "slug",
            "description",
        ]

    def create(self, validated_data):

        request = self.context["request"]

        return create_organization(
            **validated_data,
            created_by=request.user
        )


class OrganizationUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Organization

        fields = [
            "name",
            "slug",
            "description",
        ]


class MembershipSerializer(serializers.ModelSerializer):

    user_email = serializers.EmailField(
        source="user.email",
        read_only=True
    )

    user_full_name = serializers.CharField(
        source="user.full_name",
        read_only=True
    )

    class Meta:
        model = Membership

        fields = [
            "id",
            "user_email",
            "user_full_name",
            "role",
            "status",
            "joined_at",
            "created_at",
        ]

        read_only_fields = fields


class InviteMemberSerializer(serializers.Serializer):

    email = serializers.EmailField()

    role = serializers.ChoiceField(
        choices=Membership.Role.choices,
        default=Membership.Role.VIEWER
    )

    def validate_email(self, value):

        try:
            user = User.objects.get(email__iexact=value)

        except User.DoesNotExist:
            raise serializers.ValidationError(
                "This user does not have an AEGISVISION account yet."
            )

        request = self.context["request"]

        if user.pk == request.user.pk:
            raise serializers.ValidationError(
                "You cannot invite yourself."
            )

        self.target_user = user

        return user.email

    def validate(self, attrs):

        organization = self.context["organization"]
        actor_membership = self.context["actor_membership"]

        role = attrs["role"]

        if role == Membership.Role.OWNER:
            raise serializers.ValidationError({
                "role": "Ownership can only be transferred separately."
            })

        if (
            actor_membership.role == Membership.Role.ADMIN
            and role == Membership.Role.ADMIN
        ):
            raise serializers.ValidationError({
                "role": "Only the organization owner can invite an admin."
            })

        if Membership.objects.filter(
            organization=organization,
            user=self.target_user
        ).exists():
            raise serializers.ValidationError({
                "email": "This user already has a membership record."
            })

        return attrs

    def create(self, validated_data):

        return Membership.objects.create(
            organization=self.context["organization"],
            user=self.target_user,
            role=validated_data["role"],
            status=Membership.Status.INVITED,
            invited_by=self.context["request"].user
        )


class MembershipUpdateSerializer(serializers.ModelSerializer):

    class Meta:
        model = Membership

        fields = [
            "role",
            "status",
        ]

    def validate(self, attrs):

        target = self.instance
        actor = self.context["actor_membership"]

        if target.role == Membership.Role.OWNER:
            raise serializers.ValidationError(
                "Owner membership cannot be modified here."
            )

        if target.user_id == actor.user_id:
            raise serializers.ValidationError(
                "You cannot modify your own membership here."
            )

        if (
            actor.role == Membership.Role.ADMIN
            and target.role == Membership.Role.ADMIN
        ):
            raise serializers.ValidationError(
                "Admins cannot modify other admin memberships."
            )

        new_role = attrs.get("role", target.role)

        if new_role == Membership.Role.OWNER:
            raise serializers.ValidationError({
                "role": "Use the ownership transfer process instead."
            })

        if (
            actor.role == Membership.Role.ADMIN
            and new_role == Membership.Role.ADMIN
        ):
            raise serializers.ValidationError({
                "role": "Admins cannot assign the admin role."
            })

        new_status = attrs.get("status")

        if new_status == Membership.Status.INVITED:
            raise serializers.ValidationError({
                "status": "Use the invitation process for new memberships."
            })

        return attrs