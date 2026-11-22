from django.utils import timezone
from django.shortcuts import get_object_or_404

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied

from .models import Organization, Membership

from .serializers import (
    OrganizationSerializer,
    OrganizationCreateSerializer,
    OrganizationUpdateSerializer,
    MembershipSerializer,
    InviteMemberSerializer,
    MembershipUpdateSerializer,
)

from .permissions import (
    IsOrganizationMember,
    CanManageMembers,
)


def request_organization(view):
    return view.organization



class OrganizationListCreateView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        organizations = Organization.objects.filter(
            memberships__user=request.user,
            memberships__status=Membership.Status.ACTIVE,
            is_active=True
        ).distinct()

        serializer = OrganizationSerializer(
            organizations,
            many=True
        )

        return Response(serializer.data)

    def post(self, request):

        serializer = OrganizationCreateSerializer(
            data=request.data,
            context={"request": request}
        )

        serializer.is_valid(raise_exception=True)

        organization = serializer.save()

        return Response(
            OrganizationSerializer(organization).data,
            status=status.HTTP_201_CREATED
        )


class OrganizationDetailView(APIView):

    def get_permissions(self):

        if self.request.method == "PATCH":
            return [CanManageMembers()]

        return [IsOrganizationMember()]

    def get(self, request, organization_id):

        serializer = OrganizationSerializer(
            request_organization(self)
        )

        return Response(serializer.data)

    def patch(self, request, organization_id):

        organization = request_organization(self)

        serializer = OrganizationUpdateSerializer(
            organization,
            data=request.data,
            partial=True
        )

        serializer.is_valid(raise_exception=True)

        organization = serializer.save()

        return Response(
            OrganizationSerializer(organization).data
        )


class OrganizationMembersView(APIView):

    permission_classes = [CanManageMembers]

    def get(self, request, organization_id):

        members = Membership.objects.filter(
            organization=self.organization
        ).select_related("user")

        serializer = MembershipSerializer(
            members,
            many=True
        )

        return Response(serializer.data)

    def post(self, request, organization_id):

        serializer = InviteMemberSerializer(
            data=request.data,
            context={
                "request": request,
                "organization": self.organization,
                "actor_membership": self.membership,
            }
        )

        serializer.is_valid(raise_exception=True)

        membership = serializer.save()

        return Response(
            MembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED
        )


class MembershipDetailView(APIView):

    permission_classes = [CanManageMembers]

    def get_membership(self, membership_id):

        return get_object_or_404(
            Membership.objects.select_related("user"),
            pk=membership_id,
            organization=self.organization
        )

    def patch(self, request, organization_id, membership_id):

        membership = self.get_membership(membership_id)

        serializer = MembershipUpdateSerializer(
            membership,
            data=request.data,
            partial=True,
            context={
                "actor_membership": self.membership
            }
        )

        serializer.is_valid(raise_exception=True)

        membership = serializer.save()

        return Response(
            MembershipSerializer(membership).data
        )

    def delete(self, request, organization_id, membership_id):

        membership = self.get_membership(membership_id)

        if membership.role == Membership.Role.OWNER:
            raise PermissionDenied(
                "The organization owner cannot be removed."
            )

        if membership.user_id == request.user.pk:
            raise PermissionDenied(
                "You cannot remove your own membership here."
            )

        if (
            self.membership.role == Membership.Role.ADMIN
            and membership.role == Membership.Role.ADMIN
        ):
            raise PermissionDenied(
                "Admins cannot remove other admins."
            )

        membership.delete()

        return Response(
            status=status.HTTP_204_NO_CONTENT
        )


class AcceptInvitationView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, membership_id):

        membership = get_object_or_404(
            Membership.objects.select_related("organization"),
            pk=membership_id,
            user=request.user,
            status=Membership.Status.INVITED,
            organization__is_active=True
        )

        membership.status = Membership.Status.ACTIVE
        membership.joined_at = timezone.now()

        membership.save(
            update_fields=[
                "status",
                "joined_at",
                "updated_at",
            ]
        )

        return Response({
            "message": "Invitation accepted successfully.",
            "organization": membership.organization.name,
            "role": membership.role,
        })