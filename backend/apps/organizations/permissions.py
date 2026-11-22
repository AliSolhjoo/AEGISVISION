from uuid import UUID

from rest_framework.permissions import BasePermission

from .models import Organization, Membership


class IsOrganizationMember(BasePermission):
    """
    Allows access only to active members
    of the selected active organization.
    """

    message = "You are not an active member of this organization."

    allowed_roles = None

    def has_permission(self, request, view):

        user = request.user

        if not user.is_authenticated or not user.is_active:
            return False

        organization_id = (
            view.kwargs.get("organization_id")
            or request.headers.get("X-Organization-ID")
        )

        if not organization_id:
            return False

        try:
            organization_id = UUID(str(organization_id))
        except (ValueError, TypeError, AttributeError):
            return False

        organization = Organization.objects.filter(
            pk=organization_id,
            is_active=True
        ).first()

        if organization is None:
            return False

        membership = Membership.objects.filter(
            organization=organization,
            user=user,
            status=Membership.Status.ACTIVE
        ).select_related(
            "organization"
        ).first()

        if membership is None:
            return False

        if (
            self.allowed_roles is not None
            and membership.role not in self.allowed_roles
        ):
            return False

        view.organization = organization
        view.membership = membership

        return True

    def has_object_permission(self, request, view, obj):

        if not hasattr(view, "organization"):
            return False

        if isinstance(obj, Organization):
            object_organization_id = obj.pk
        else:
            object_organization_id = getattr(
                obj,
                "organization_id",
                None
            )

        return object_organization_id == view.organization.pk


class CanManageMembers(IsOrganizationMember):

    allowed_roles = {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
    }


class CanManageCameras(IsOrganizationMember):

    allowed_roles = {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.OPERATOR,
    }


class CanManageEventRules(IsOrganizationMember):

    allowed_roles = {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
    }


class CanAcknowledgeEvents(IsOrganizationMember):

    allowed_roles = {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.OPERATOR,
    }


class CanViewAnalytics(IsOrganizationMember):

    allowed_roles = {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.OPERATOR,
        Membership.Role.ANALYST,
        Membership.Role.VIEWER,
    }