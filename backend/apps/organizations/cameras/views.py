from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import SAFE_METHODS
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Camera
from .permissions import CanViewCameras
from apps.organizations.permissions import CanManageCameras
from .serializers import CameraSerializer


class CameraListCreateView(APIView):
    """List or register cameras within the organization in the URL."""

    def get_permissions(self):
        permission_class = (
            CanViewCameras if self.request.method in SAFE_METHODS
            else CanManageCameras
        )
        return [permission_class()]

    def get(self, request, organization_id):
        cameras = Camera.objects.filter(
            organization=self.organization
        ).select_related("created_by", "organization")
        serializer = CameraSerializer(cameras, many=True)
        return Response(serializer.data)

    def post(self, request, organization_id):
        serializer = CameraSerializer(
            data=request.data,
            context={"organization": self.organization},
        )
        serializer.is_valid(raise_exception=True)
        camera = serializer.save(
            organization=self.organization,
            created_by=request.user,
        )
        return Response(
            CameraSerializer(camera).data,
            status=status.HTTP_201_CREATED,
        )


class CameraDetailView(APIView):
    """Retrieve, update or disable a camera, scoped to one organization."""

    def get_permissions(self):
        permission_class = (
            CanViewCameras if self.request.method in SAFE_METHODS
            else CanManageCameras
        )
        return [permission_class()]

    def get_camera(self, camera_id):
        return get_object_or_404(
            Camera.objects.select_related("created_by", "organization"),
            pk=camera_id,
            organization=self.organization,
        )

    def get(self, request, organization_id, camera_id):
        camera = self.get_camera(camera_id)
        return Response(CameraSerializer(camera).data)

    def patch(self, request, organization_id, camera_id):
        camera = self.get_camera(camera_id)
        if not camera.is_enabled:
            return Response(
                {"detail": "Disabled cameras cannot be edited."},
                status=status.HTTP_409_CONFLICT,
            )
        serializer = CameraSerializer(
            camera,
            data=request.data,
            partial=True,
            context={"organization": self.organization},
        )
        serializer.is_valid(raise_exception=True)
        camera = serializer.save()
        return Response(CameraSerializer(camera).data)

    def delete(self, request, organization_id, camera_id):
        camera = self.get_camera(camera_id)
        if not camera.is_enabled:
            return Response(status=status.HTTP_204_NO_CONTENT)
        camera.is_enabled = False
        camera.status = Camera.Status.DISABLED
        camera.save(update_fields=["is_enabled", "status", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)
