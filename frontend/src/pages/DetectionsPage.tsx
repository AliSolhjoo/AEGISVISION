import { t, useLanguage } from '../i18n';
import { useEffect, useMemo, useState } from 'react';
import { Activity, Cpu, Radar, RefreshCw, ScanEye, Sparkles } from 'lucide-react';
import { api, describeApiError, toApiPath } from '../lib/api';
import type { DetectionFrame, DetectionRun, VideoAsset } from '../lib/types';
import { formatDate, formatDuration, formatRelative, titleCase } from '../lib/format';
import { useOrganizations } from '../context/OrganizationContext';
import { Button, EmptyState, FormField, LoadingState, PageHeader, SectionHeading } from '../components/Ui';
import StatusBadge from '../components/StatusBadge';
import AuthenticatedImage from '../components/AuthenticatedImage';
import { notify } from '../components/Toast';

export default function DetectionsPage() {
  
  useLanguage();
const { activeOrganization } = useOrganizations();
  const [videos, setVideos] = useState<VideoAsset[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState('');
  const [runs, setRuns] = useState<DetectionRun[]>([]);
  const [selectedRunId, setSelectedRunId] = useState('');
  const [frames, setFrames] = useState<DetectionFrame[]>([]);
  const [loading, setLoading] = useState(true);
  const [runsLoading, setRunsLoading] = useState(false);
  const [framesLoading, setFramesLoading] = useState(false);
  const [error, setError] = useState('');
  const [threshold, setThreshold] = useState('0.55');
  const [maxFrames, setMaxFrames] = useState('120');
  const [device, setDevice] = useState('auto');
  const [creating, setCreating] = useState(false);

  const selectedVideo = videos.find((item) => String(item.id) === selectedVideoId) || null;
  const selectedRun = runs.find((item) => String(item.id) === selectedRunId) || null;

  const loadVideos = async () => {
    if (!activeOrganization) { setVideos([]); setLoading(false); return; }
    setLoading(true); setError('');
    try {
      const data = await api.get<VideoAsset[]>(`/api/organizations/${activeOrganization.id}/videos/`);
      setVideos(data);
      if (!selectedVideoId && data.length) setSelectedVideoId(String(data[0].id));
    } catch (err) { setError(describeApiError(err)); }
    finally { setLoading(false); }
  };

  const loadRuns = async () => {
    if (!activeOrganization || !selectedVideoId) { setRuns([]); setSelectedRunId(''); return; }
    setRunsLoading(true); setError('');
    try {
      const data = await api.get<DetectionRun[]>(`/api/organizations/${activeOrganization.id}/videos/${selectedVideoId}/detections/`);
      setRuns(data);
      setSelectedRunId((current) => data.some((item) => String(item.id) === current) ? current : data[0] ? String(data[0].id) : '');
    } catch (err) { setError(describeApiError(err)); }
    finally { setRunsLoading(false); }
  };

  const loadFrames = async (run: DetectionRun | null) => {
    if (!activeOrganization || !selectedVideoId || !run || run.status !== 'completed') { setFrames([]); return; }
    setFramesLoading(true);
    try {
      setFrames(await api.get<DetectionFrame[]>(`/api/organizations/${activeOrganization.id}/videos/${selectedVideoId}/detections/${run.id}/frames/`));
    } catch (err) { setError(describeApiError(err)); }
    finally { setFramesLoading(false); }
  };

  const refreshSelectedRun = async () => {
    if (!activeOrganization || !selectedVideoId || !selectedRunId) return;
    try {
      const updated = await api.get<DetectionRun>(`/api/organizations/${activeOrganization.id}/videos/${selectedVideoId}/detections/${selectedRunId}/`);
      setRuns((current) => current.map((run) => run.id === updated.id ? updated : run));
    } catch (err) { setError(describeApiError(err)); }
  };

  useEffect(() => {
    setSelectedVideoId('');
    setSelectedRunId('');
    setRuns([]);
    setFrames([]);
    void loadVideos();
  }, [activeOrganization?.id]);
  useEffect(() => { void loadRuns(); }, [activeOrganization?.id, selectedVideoId]);
  useEffect(() => { void loadFrames(selectedRun); }, [activeOrganization?.id, selectedVideoId, selectedRunId, selectedRun?.status]);
  useEffect(() => {
    if (!selectedRun || !['queued', 'processing'].includes(selectedRun.status)) return;
    const timer = window.setInterval(() => { void refreshSelectedRun(); }, 6000);
    return () => window.clearInterval(timer);
  }, [activeOrganization?.id, selectedVideoId, selectedRunId, selectedRun?.status]);

  const createRun = async () => {
    if (!activeOrganization || !selectedVideo) return;
    setCreating(true); setError('');
    try {
      const created = await api.post<DetectionRun>(`/api/organizations/${activeOrganization.id}/videos/${selectedVideo.id}/detections/`, {
        confidence_threshold: Number(threshold), max_frames: Number(maxFrames), requested_device: device,
      });
      notify('Detection run queued', `Run #${created.id} is waiting for the backend worker.`);
      setRuns((current) => [created, ...current]); setSelectedRunId(String(created.id));
    } catch (err) { const msg = describeApiError(err); setError(msg); notify('Could not queue detection', msg, 'error'); }
    finally { setCreating(false); }
  };

  const labelStats = useMemo(() => {
    const counts = new Map<string, number>();
    frames.forEach((frame) => frame.detections.forEach((detection) => counts.set(detection.label, (counts.get(detection.label) || 0) + 1)));
    return [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [frames]);

  return <>
    <PageHeader eyebrow={t("AI ENGINE / OBJECT DETECTION")} title={t("AI detections")} description={t("Run object detection on extracted frames and inspect annotated visual evidence.")} actions={<Button variant="secondary" onClick={() => { void loadVideos(); void loadRuns(); void refreshSelectedRun(); }}><RefreshCw size={16}/> {t("Refresh")}</Button>}/>
    {loading ? <LoadingState/> : error && videos.length === 0 ? <div className="notice notice-error">{t(error)}</div> : videos.length === 0 ? <EmptyState title={t("No video assets available")} description={t("Upload a video and finish frame extraction before starting AI detection.")}/> : <>
      <section className="panel detection-launcher">
        <div className="detection-launcher-header"><div className="launcher-icon"><ScanEye size={22}/></div><div><div className="eyebrow">{t("NEW ANALYSIS")}</div><h2>{t("Configure detection run")}</h2><p>{t("Select a processed video and configure model inference.")}</p></div></div>
        <div className="detection-config-grid">
          <FormField label={t("Source video")}><select value={selectedVideoId} onChange={(e) => setSelectedVideoId(e.target.value)}>{videos.map((video) => <option key={video.id} value={video.id}>{video.name} {t("· #")}{video.id} {t("· ")}{t(titleCase(video.status))}</option>)}</select></FormField>
          <FormField label={t("Confidence threshold")} hint={t("Higher threshold returns fewer, more confident detections")}><input type="number" min="0.05" max="0.99" step="0.05" value={threshold} onChange={(e) => setThreshold(e.target.value)}/></FormField>
          <FormField label={t("Maximum frames")} hint={t("1–300 frames")}><input type="number" min="1" max="300" value={maxFrames} onChange={(e) => setMaxFrames(e.target.value)}/></FormField>
          <FormField label={t("Inference device")}><select value={device} onChange={(e) => setDevice(e.target.value)}><option value="auto">{t("Automatic")}</option><option value="cpu">{t("CPU")}</option><option value="cuda">{t("CUDA GPU")}</option></select></FormField>
        </div>
        <div className="launcher-footer"><div className="model-info"><Cpu size={15}/><span>{t("Faster R-CNN · MobileNetV3 · COCO weights")}</span></div><Button onClick={() => void createRun()} disabled={creating || !selectedVideo || selectedVideo.status !== 'completed'}>{t(creating ? 'Queueing…' : 'Start detection run')}<Sparkles size={16}/></Button></div>
        {selectedVideo && selectedVideo.status !== 'completed' && <div className="notice notice-warning"><Activity size={16}/> {t("This video must complete frame extraction before detection can start. Current status: ")}{t(titleCase(selectedVideo.status))}{t(".")}</div>}
        {error && <div className="notice notice-error">{t(error)}</div>}
      </section>
      <div className="dashboard-grid detection-results-grid">
        <section className="panel runs-panel"><SectionHeading title={t("Detection runs")} subtitle={t("Analysis history for selected asset")}/>
          {runsLoading ? <LoadingState label={t("Loading detection runs…")}/> : runs.length === 0 ? <EmptyState title={t("No detection runs")} description={t("Start a run to analyze the extracted frames from this video.")}/> : <div className="run-list">{runs.map((run) => <button className={`run-row ${String(run.id) === selectedRunId ? 'run-selected' : ''}`} key={run.id} onClick={() => setSelectedRunId(String(run.id))}><div className="run-row-icon"><Radar size={17}/></div><div className="run-row-main"><strong>{t("Run #")}{run.id}</strong><small>{formatDate(run.created_at)} {t("· ")}{run.model_name.replaceAll('_', ' ')}</small></div><StatusBadge status={run.status}/><span className="run-row-arrow">{t("›")}</span></button>)}</div>}
        </section>
        <section className="panel run-detail-panel"><SectionHeading title={t("Run details")} subtitle={t(selectedRun ? `Analysis run #${selectedRun.id}` : 'Select a detection run')}/>
          {!selectedRun ? <EmptyState title={t("No run selected")} description={t("Detection run metadata and output statistics will appear here.")}/> : <>
            <div className="run-status-line"><StatusBadge status={selectedRun.status}/><span>{t("Created ")}{formatRelative(selectedRun.created_at)}</span></div>
            <div className="run-stats-grid"><div><span>{t("Frames processed")}</span><strong>{selectedRun.frames_processed}</strong></div><div><span>{t("Objects detected")}</span><strong>{selectedRun.detections_count}</strong></div><div><span>{t("Execution device")}</span><strong>{selectedRun.actual_device || titleCase(selectedRun.requested_device)}</strong></div><div><span>{t("Threshold")}</span><strong>{Math.round(selectedRun.confidence_threshold * 100)}{t("%")}</strong></div></div>
            <div className="run-model"><Cpu size={15}/><span>{selectedRun.model_name}</span></div>
            {selectedRun.error_message && <div className="notice notice-error">{selectedRun.error_message}</div>}
            {['queued', 'processing'].includes(selectedRun.status) && <div className="worker-command"><span>{t("BACKEND WORKER COMMAND")}</span><code>python manage.py detect_video_objects --run-id {selectedRun.id}</code><small>{t("Run this in the Django backend terminal to execute this queued analysis.")}</small></div>}
          </>}
        </section>
      </div>
      {selectedRun?.status === 'completed' && <section className="panel detection-frames-panel"><SectionHeading title={t("Annotated frames")} subtitle={t(`${frames.length} frames contain visual analysis output`)}/>
        {framesLoading ? <LoadingState label={t("Loading annotated frames…")}/> : frames.length === 0 ? <EmptyState title={t("No annotated frames returned")} description={t("The run completed but has no available frame images.")}/> : <>
          {labelStats.length > 0 && <div className="label-stat-row">{labelStats.map(([label, count]) => <span className="label-stat" key={label}><i/>{t(titleCase(label))} <strong>{count}</strong></span>)}</div>}
          <div className="annotated-grid">{frames.map((frame) => <article className="annotated-card" key={frame.id}><AuthenticatedImage src={toApiPath(frame.image_url)} alt={`Annotated frame ${frame.source_frame_number}`} className="annotated-image"/><div className="annotated-info"><div><strong>{t("Frame ")}{frame.source_frame_number}</strong><small>{formatDuration(frame.timestamp_seconds)} {t("timestamp")}</small></div><span className="count-pill">{frame.detections_count} {t("objects")}</span></div><div className="annotated-tags">{frame.detections.slice(0, 5).map((detection) => <span key={detection.id}>{t(titleCase(detection.label))} {t("· ")}{Math.round(detection.confidence * 100)}{t("%")}</span>)}</div></article>)}</div>
        </>}
      </section>}
      {selectedRun && ['queued', 'processing'].includes(selectedRun.status) && <div className="notice notice-info"><Activity size={16}/> {t("This page refreshes the selected run status every six seconds while it is queued or processing.")}</div>}
    </>}
  </>;
}
