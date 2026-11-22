from django.contrib import admin
from django.urls import path, include


urlpatterns = [
    path("api/auth/", include("apps.accounts.auth_urls")), 

    path("api/video-analysis/", include("apps.organizations.cameras.video_analysis_urls")),

    path("admin/", admin.site.urls),

    path(
        "api/organizations/",
        include("apps.organizations.urls")
    ),

    path(
        "api-auth/",
        include("rest_framework.urls")
    ),

]