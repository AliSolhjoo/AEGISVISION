from rest_framework.permissions import SAFE_METHODS

from apps.organizations.models import Membership
from apps.organizations.permissions import IsOrganizationMember, CanManageCameras


class CanViewCameras(IsOrganizationMember):
    allowed_roles = {
        Membership.Role.OWNER,
        Membership.Role.ADMIN,
        Membership.Role.OPERATOR,
        Membership.Role.ANALYST,
        Membership.Role.VIEWER,
    }


def camera_permission_for_method(method):
    if method in SAFE_METHODS:
        return CanViewCameras
    return CanManageCameras
