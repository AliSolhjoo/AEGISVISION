from django.urls import path

from .video_analysis_api import (
    VideoAnalysisResultView,
    VideoAnalysisStartView,
    VideoAnalysisStatusView,
    VideoAnalysisUploadView,
)

app_name = "video_analysis"

urlpatterns = [
    path("upload/", VideoAnalysisUploadView.as_view(), name="upload"),
    path("assets/<int:asset_id>/start/", VideoAnalysisStartView.as_view(), name="start"),
    path("assets/<int:asset_id>/status/", VideoAnalysisStatusView.as_view(), name="status"),
    path("assets/<int:asset_id>/result/", VideoAnalysisResultView.as_view(), name="result"),
]
