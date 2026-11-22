export interface User {
  id: number | string;
  email: string;
  first_name: string;
  last_name: string;
  full_name: string;
  date_joined: string;
}

export interface Tokens {
  access: string;
  refresh: string;
  user?: User;
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  description: string;
  is_active: boolean;
  created_by_email?: string;
  member_count?: number;
  created_at: string;
  updated_at: string;
}

export type Role = 'owner' | 'admin' | 'operator' | 'analyst' | 'viewer';
export type MembershipStatus = 'active' | 'invited' | 'suspended';

export interface Membership {
  id: string;
  user_email: string;
  user_full_name: string;
  role: Role;
  status: MembershipStatus;
  joined_at: string | null;
  created_at: string;
}

export interface Camera {
  id: number;
  name: string;
  code: string;
  description: string;
  location: string;
  source_type: 'rtsp' | 'rtsps' | 'browser';
  status: 'pending' | 'online' | 'offline' | 'error' | 'disabled';
  is_enabled: boolean;
  target_fps: number;
  confidence_threshold: number;
  has_stream_credentials: boolean;
  last_seen_at: string | null;
  created_by_email?: string;
  created_at: string;
  updated_at: string;
}

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';


export type LiveCameraStatus = 'stopped' | 'starting' | 'online' | 'reconnecting' | 'error';
export interface CameraLiveState {
  camera_id: number;
  camera_name: string;
  status: LiveCameraStatus;
  is_requested: boolean;
  worker_online: boolean;
  session_id: string;
  frame_number: number;
  frames_processed: number;
  objects_count: number;
  tracks_count: number;
  fps_actual: number;
  width: number | null;
  height: number | null;
  latest_detections: Array<{ track_number: number; label: string; class_id: number; confidence: number; bounding_box: number[] }>;
  last_error: string;
  session_started_at: string | null;
  last_frame_at: string | null;
  last_inference_at: string | null;
  snapshot_available: boolean;
  updated_at: string | null;
}

export interface CameraAnalyticsRule {
  id: number;
  asset_id: number | null;
  camera_id: number | null;
  scope: 'camera' | 'asset';
  name: string;
  rule_type: 'zone_intrusion' | 'line_crossing' | 'loitering';
  geometry: { polygon?: number[][]; line?: number[][] };
  labels: string[];
  minimum_confidence: number;
  anchor: 'bottom_center' | 'center';
  direction: 'both' | 'negative_to_positive' | 'positive_to_negative';
  dwell_seconds: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CameraLiveEvent {
  id: number; camera_id: number; camera_name: string; rule_id: number | null; rule_name: string;
  event_type: string; track_number: number; label: string; timestamp_seconds: number;
  frame_number: number; confidence: number; details: Record<string, unknown>;
  severity: 'critical' | 'high' | 'medium' | 'low';
  status: 'new' | 'acknowledged' | 'investigating' | 'resolved' | 'false_positive';
  assigned_to_id: number | null; assigned_to: { id: number; email: string; full_name: string } | null;
  occurred_at: string; created_at: string;
}

export interface VideoJob {
  id: number;
  status: JobStatus;
  frame_interval_seconds: number;
  max_frames: number;
  effective_interval_seconds: number | null;
  frame_count: number;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface VideoAsset {
  id: number;
  name: string;
  camera_id: number | null;
  original_filename: string;
  content_type: string;
  file_size: number;
  sha256: string;
  status: JobStatus;
  duration_seconds: number | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  uploaded_by_email?: string;
  processing_job?: VideoJob;
  frames_count?: number;
  created_at: string;
  updated_at: string;
}

export interface VideoFrame {
  id: number;
  frame_number: number;
  timestamp_seconds: number;
  width: number;
  height: number;
  image_endpoint: string;
}

export interface DetectionRun {
  id: number;
  asset_id: number;
  status: JobStatus;
  model_name: string;
  confidence_threshold: number;
  max_frames: number;
  requested_device: string;
  actual_device: string;
  frames_processed: number;
  detections_count: number;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ObjectDetection {
  id: number;
  class_id: number;
  label: string;
  confidence: number;
  bounding_box: number[];
  created_at: string;
}

export interface DetectionFrame {
  id: number;
  source_frame_number: number;
  timestamp_seconds: number;
  detections_count: number;
  image_url: string;
  detections: ObjectDetection[];
  created_at: string;
}

export interface ApiErrorShape {
  detail?: string;
  message?: string;
  [key: string]: unknown;
}


export interface TrackingRun {
  id: number;
  detection_run_id: number;
  video_id: number;
  status: JobStatus;
  tracker_name: string;
  iou_threshold: number;
  max_gap_frames: number;
  frames_processed: number;
  tracks_count: number;
  observations_count: number;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TrackObservation {
  id: number;
  detection_id: number;
  frame_number: number;
  timestamp_seconds: number;
  confidence: number;
  bounding_box: number[];
  created_at: string;
}

export interface ObjectTrack {
  id: number;
  track_number: number;
  class_id: number;
  label: string;
  status: string;
  first_frame_number: number;
  last_frame_number: number;
  first_timestamp_seconds: number;
  last_timestamp_seconds: number;
  observations_count: number;
  created_at: string;
  observations?: TrackObservation[];
}
