from django.test import TestCase

from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts.models import User
from .models import Organization, Membership
from .permissions import (
    IsOrganizationMember,
    CanManageMembers,
    CanManageCameras,
    CanManageEventRules,
    CanAcknowledgeEvents,
    CanViewAnalytics,
)

from django.urls import reverse
from rest_framework.test import APITestCase



class OrganizationPermissionTests(TestCase):

    def setUp(self):

        self.factory = APIRequestFactory()

        self.owner = User.objects.create_user(
            email="owner@test.com",
            password="StrongPassword123!"
        )

        self.operator = User.objects.create_user(
            email="operator@test.com",
            password="StrongPassword123!"
        )

        self.viewer = User.objects.create_user(
            email="viewer@test.com",
            password="StrongPassword123!"
        )

        self.stranger = User.objects.create_user(
            email="stranger@test.com",
            password="StrongPassword123!"
        )

        self.organization = Organization.objects.create(
            name="Test Organization",
            slug="test-organization",
            created_by=self.owner
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.operator,
            role=Membership.Role.OPERATOR,
            status=Membership.Status.ACTIVE
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.viewer,
            role=Membership.Role.VIEWER,
            status=Membership.Status.ACTIVE
        )

    def make_request(self, user, permission_class):

        class ProtectedView(APIView):

            def get(self, request):
                return Response({"access": "granted"})

        ProtectedView.permission_classes = [permission_class]

        request = self.factory.get(
            "/api/test/",
            HTTP_X_ORGANIZATION_ID=str(self.organization.id)
        )

        force_authenticate(request, user=user)

        return ProtectedView.as_view()(request)

    def test_owner_can_manage_members(self):

        response = self.make_request(
            self.owner,
            CanManageMembers
        )

        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_manage_members(self):

        response = self.make_request(
            self.viewer,
            CanManageMembers
        )

        self.assertEqual(response.status_code, 403)

    def test_operator_can_manage_cameras(self):

        response = self.make_request(
            self.operator,
            CanManageCameras
        )

        self.assertEqual(response.status_code, 200)

    def test_viewer_cannot_manage_cameras(self):

        response = self.make_request(
            self.viewer,
            CanManageCameras
        )

        self.assertEqual(response.status_code, 403)

    def test_analyst_permission_policy(self):

        analyst = User.objects.create_user(
            email="analyst@test.com",
            password="StrongPassword123!"
        )

        Membership.objects.create(
            organization=self.organization,
            user=analyst,
            role=Membership.Role.ANALYST
        )

        response = self.make_request(
            analyst,
            CanViewAnalytics
        )

        self.assertEqual(response.status_code, 200)

        response = self.make_request(
            analyst,
            CanManageCameras
        )

        self.assertEqual(response.status_code, 403)

    def test_non_member_cannot_access_organization(self):

        response = self.make_request(
            self.stranger,
            IsOrganizationMember
        )

        self.assertEqual(response.status_code, 403)

    def test_viewer_can_view_analytics(self):

        response = self.make_request(
            self.viewer,
            CanViewAnalytics
        )

        self.assertEqual(response.status_code, 200)

    def test_invalid_organization_id_is_rejected(self):

        class ProtectedView(APIView):

            permission_classes = [IsOrganizationMember]

            def get(self, request):
                return Response({"access": "granted"})

        request = self.factory.get(
            "/api/test/",
            HTTP_X_ORGANIZATION_ID="not-a-valid-uuid"
        )

        force_authenticate(request, user=self.owner)

        response = ProtectedView.as_view()(request)

        self.assertEqual(response.status_code, 403)

    def test_inactive_membership_is_rejected(self):

        membership = Membership.objects.get(
            organization=self.organization,
            user=self.operator
        )

        membership.status = Membership.Status.SUSPENDED
        membership.save()

        response = self.make_request(
            self.operator,
            IsOrganizationMember
        )

        self.assertEqual(response.status_code, 403)

    def test_inactive_organization_is_rejected(self):

        self.organization.is_active = False
        self.organization.save()

        response = self.make_request(
            self.owner,
            IsOrganizationMember
        )

        self.assertEqual(response.status_code, 403)
        
class OrganizationAPITests(APITestCase):

    def setUp(self):

        self.owner = User.objects.create_user(
            email="api-owner@test.com",
            password="StrongPassword123!"
        )

        self.viewer = User.objects.create_user(
            email="api-viewer@test.com",
            password="StrongPassword123!"
        )

        self.invitee = User.objects.create_user(
            email="api-invitee@test.com",
            password="StrongPassword123!"
        )

        self.organization = Organization.objects.create(
            name="API Test Organization",
            slug="api-test-organization",
            created_by=self.owner
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.owner,
            role=Membership.Role.OWNER,
            status=Membership.Status.ACTIVE
        )

        Membership.objects.create(
            organization=self.organization,
            user=self.viewer,
            role=Membership.Role.VIEWER,
            status=Membership.Status.ACTIVE
        )

        self.client.force_authenticate(user=self.owner)

    def test_owner_can_list_organizations(self):

        response = self.client.get(
            reverse("organizations:list-create")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

    def test_owner_can_create_organization(self):

        response = self.client.post(
            reverse("organizations:list-create"),
            {
                "name": "Factory North",
                "slug": "factory-north",
                "description": "North factory"
            },
            format="json"
        )

        self.assertEqual(response.status_code, 201)

        organization = Organization.objects.get(
            slug="factory-north"
        )

        self.assertTrue(
            Membership.objects.filter(
                organization=organization,
                user=self.owner,
                role=Membership.Role.OWNER,
                status=Membership.Status.ACTIVE
            ).exists()
        )

    def test_non_member_cannot_view_organization(self):

        self.client.force_authenticate(user=self.invitee)

        response = self.client.get(
            reverse(
                "organizations:detail",
                kwargs={
                    "organization_id": self.organization.id
                }
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_owner_can_invite_existing_user(self):

        response = self.client.post(
            reverse(
                "organizations:members",
                kwargs={
                    "organization_id": self.organization.id
                }
            ),
            {
                "email": self.invitee.email,
                "role": Membership.Role.VIEWER
            },
            format="json"
        )

        self.assertEqual(response.status_code, 201)

        self.assertTrue(
            Membership.objects.filter(
                organization=self.organization,
                user=self.invitee,
                status=Membership.Status.INVITED
            ).exists()
        )

    def test_invited_user_can_accept_invitation(self):

        invitation = Membership.objects.create(
            organization=self.organization,
            user=self.invitee,
            role=Membership.Role.VIEWER,
            status=Membership.Status.INVITED,
            invited_by=self.owner
        )

        self.client.force_authenticate(user=self.invitee)

        response = self.client.post(
            reverse(
                "organizations:invitation-accept",
                kwargs={
                    "membership_id": invitation.id
                }
            )
        )

        self.assertEqual(response.status_code, 200)

        invitation.refresh_from_db()

        self.assertEqual(
            invitation.status,
            Membership.Status.ACTIVE
        )

        self.assertIsNotNone(invitation.joined_at)