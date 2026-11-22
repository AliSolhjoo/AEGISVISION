import { t, useLanguage } from '../i18n';
import { useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Activity, Crosshair, GitBranch, RefreshCw, ScanLine, Waypoints } from 'lucide-react';
import { api, describeApiError } from '../lib/api';
import type { DetectionRun, ObjectTrack, TrackingRun, VideoAsset } from '../lib/types';
import { formatDate, formatDuration, titleCase } from '../lib/format';
import { useOrganizations } from '../context/OrganizationContext';
import { Button, EmptyState, FormField, LoadingState, PageHeader, SectionHeading } from '../components/Ui';
import StatusBadge from '../components/StatusBadge';
import { notify } from '../components/Toast';

export default function TrackingPage() {
  useLanguage();
  const { activeOrganization } = useOrganizations();
  const [videos, setVideos] = useState<VideoAsset[]>([]);
  const [selectedVideoId, setSelectedVideoId] = useState('');
  const [detectionRuns, setDetectionRuns] = useState<DetectionRun[]>([]);
  const [selectedDetectionRunId, setSelectedDetectionRunId] = useState('');
  const [trackingRuns, setTrackingRuns] = useState<TrackingRun[]>([]);
  const [selectedTrackingRunId, setSelectedTrackingRunId] = useState('');
  const [tracks, setTracks] = useState<ObjectTrack[]>([]);
  const [selectedTrackId, setSelectedTrackId] = useState('');
  const [selectedTrack, setSelectedTrack] = useState<ObjectTrack | null>(null);
  const [iouThreshold, setIouThreshold] = useState('0.30');
  const [maxGapFrames, setMaxGapFrames] = useState('2');
  const [loading, setLoading] = useState(true);
  const [runsLoading, setRunsLoading] = useState(false);
  const [tracksLoading, setTracksLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  const selectedDetectionRun = useMemo(
    () => detectionRuns.find((item) => String(item.id) === selectedDetectionRunId) || null,
    [detectionRuns, selectedDetectionRunId],
  );
  const selectedTrackingRun = useMemo(
    () => trackingRuns.find((item) => String(item.id) === selectedTrackingRunId) || null,
    [trackingRuns, selectedTrackingRunId],
  );

  const detectionBase = (videoId: string, detectionRunId: string) =>
    `/api/organizations/${activeOrganization?.id}/videos/${videoId}/detections/${detectionRunId}`;

  const loadVideos = async () => {
    if (!activeOrganization) { setVideos([]); setLoading(false); return; }
    setLoading(true); setError('');
    try {
      const data = await api.get<VideoAsset[]>(`/api/organizations/${activeOrganization.id}/videos/`);
      setVideos(data);
      setSelectedVideoId((current) => data.some((item) => String(item.id) === current) ? current : data[0] ? String(data[0].id) : '');
    } catch (err) { setError(describeApiError(err)); }
    finally { setLoading(false); }
  };

  const loadDetectionRuns = async () => {
    if (!activeOrganization || !selectedVideoId) { setDetectionRuns([]); setSelectedDetectionRunId(''); return; }
    setRunsLoading(true); setError('');
    try {
      const data = await api.get<DetectionRun[]>(`/api/organizations/${activeOrganization.id}/videos/${selectedVideoId}/detections/`);
      const completed = data.filter((item) => item.status === 'completed');
      setDetectionRuns(completed);
      setSelectedDetectionRunId((current) => completed.some((item) => String(item.id) === current) ? current : completed[0] ? String(completed[0].id) : '');
    } catch (err) { setError(describeApiError(err)); }
    finally { setRunsLoading(false); }
  };

  const loadTrackingRuns = async () => {
    if (!activeOrganization || !selectedVideoId || !selectedDetectionRunId) { setTrackingRuns([]); setSelectedTrackingRunId(''); return; }
    setRunsLoading(true); setError('');
    try {
      const data = await api.get<TrackingRun[]>(`${detectionBase(selectedVideoId, selectedDetectionRunId)}/tracking/`);
      setTrackingRuns(data);
      setSelectedTrackingRunId((current) => data.some((item) => String(item.id) === current) ? current : data[0] ? String(data[0].id) : '');
    } catch (err) { setError(describeApiError(err)); }
    finally { setRunsLoading(false); }
  };

  const loadTracks = async () => {
    if (!activeOrganization || !selectedVideoId || !selectedDetectionRunId || !selectedTrackingRun || selectedTrackingRun.status !== 'completed') {
      setTracks([]); setSelectedTrackId(''); setSelectedTrack(null); return;
    }
    setTracksLoading(true); setError('');
    try {
      const base = `${detectionBase(selectedVideoId, selectedDetectionRunId)}/tracking/${selectedTrackingRun.id}`;
      const data = await api.get<ObjectTrack[]>(`${base}/tracks/`);
      setTracks(data);
      setSelectedTrackId((current) => data.some((item) => String(item.id) === current) ? current : data[0] ? String(data[0].id) : '');
    } catch (err) { setError(describeApiError(err)); }
    finally { setTracksLoading(false); }
  };

  const loadTrackDetail = async () => {
    if (!activeOrganization || !selectedVideoId || !selectedDetectionRunId || !selectedTrackingRunId || !selectedTrackId) {
      setSelectedTrack(null); return;
    }
    try {
      const path = `${detectionBase(selectedVideoId, selectedDetectionRunId)}/tracking/${selectedTrackingRunId}/tracks/${selectedTrackId}/`;
      setSelectedTrack(await api.get<ObjectTrack>(path));
    } catch (err) { setError(describeApiError(err)); }
  };

  const refreshTrackingRun = async () => {
    if (!activeOrganization || !selectedVideoId || !selectedDetectionRunId || !selectedTrackingRunId) return;
    try {
      const updated = await api.get<TrackingRun>(`${detectionBase(selectedVideoId, selectedDetectionRunId)}/tracking/${selectedTrackingRunId}/`);
      setTrackingRuns((current) => current.map((item) => item.id === updated.id ? updated : item));
    } catch (err) { setError(describeApiError(err)); }
  };

  useEffect(() => {
    setSelectedVideoId(''); setSelectedDetectionRunId(''); setDetectionRuns([]);
    setTrackingRuns([]); setSelectedTrackingRunId(''); setTracks([]); setSelectedTrack(null);
    void loadVideos();
  }, [activeOrganization?.id]);
  useEffect(() => { setSelectedDetectionRunId(''); setDetectionRuns([]); setTrackingRuns([]); setSelectedTrackingRunId(''); setTracks([]); setSelectedTrack(null); void loadDetectionRuns(); }, [activeOrganization?.id, selectedVideoId]);
  useEffect(() => { setSelectedTrackingRunId(''); setTrackingRuns([]); setTracks([]); setSelectedTrack(null); void loadTrackingRuns(); }, [activeOrganization?.id, selectedVideoId, selectedDetectionRunId]);
  useEffect(() => { void loadTracks(); }, [activeOrganization?.id, selectedVideoId, selectedDetectionRunId, selectedTrackingRunId, selectedTrackingRun?.status]);
  useEffect(() => { void loadTrackDetail(); }, [activeOrganization?.id, selectedVideoId, selectedDetectionRunId, selectedTrackingRunId, selectedTrackId]);
  useEffect(() => {
    if (!selectedTrackingRun || !['queued', 'processing'].includes(selectedTrackingRun.status)) return;
    const timer = window.setInterval(() => { void refreshTrackingRun(); }, 6000);
    return () => window.clearInterval(timer);
  }, [activeOrganization?.id, selectedVideoId, selectedDetectionRunId, selectedTrackingRunId, selectedTrackingRun?.status]);

  const startTracking = async () => {
    if (!activeOrganization || !selectedVideoId || !selectedDetectionRun) return;
    setCreating(true); setError('');
    try {
      const created = await api.post<TrackingRun>(`${detectionBase(selectedVideoId, selectedDetectionRunId)}/tracking/`, {
        iou_threshold: Number(iouThreshold), max_gap_frames: Number(maxGapFrames),
      });
      notify('Tracking run queued', `Run #${created.id} is waiting for the backend worker.`);
      setTrackingRuns((current) => [created, ...current]);
      setSelectedTrackingRunId(String(created.id));
    } catch (err) { const message = describeApiError(err); setError(message); notify('Could not queue tracking', message, 'error'); }
    finally { setCreating(false); }
  };

  return <>
    <PageHeader
      eyebrow={t('OBJECT TRACKING / TEMPORAL ANALYSIS')}
      title={t('Object tracking')}
      description={t('Follow detected objects across frames within a video analysis run.')}
      actions={<Button variant="secondary" onClick={() => { void loadVideos(); void loadDetectionRuns(); void loadTrackingRuns(); }}><RefreshCw size={16}/>{t('Refresh')}</Button>}
    />
    <div className="tracking-disclaimer"><ShieldAlertIcon/><div><strong>{t('Track IDs are scoped to this tracking run only.')}</strong><p>{t('This tracker uses class-aware greedy IoU association. Track IDs are local to a single tracking run and do not identify a real person or object across separate videos.')}</p></div></div>
    {loading ? <LoadingState/> : error && videos.length === 0 ? <div className="notice notice-error">{t(error)}</div> : videos.length === 0 ? <EmptyState title={t('No video assets available')} description={t('Upload a video and finish frame extraction before starting AI detection.')}/> : <>
      <section className="panel tracking-setup-panel">
        <div className="tracking-setup-heading"><div className="launcher-icon"><Waypoints size={21}/></div><div><div className="eyebrow">{t('Tracking parameters')}</div><h2>{t('Start tracking')}</h2><p>{t('Create a tracking run to follow detected objects between frames.')}</p></div></div>
        <div className="tracking-form-grid">
          <FormField label={t('Choose a video')}><select value={selectedVideoId} onChange={(event) => setSelectedVideoId(event.target.value)}>{videos.map((video) => <option key={video.id} value={video.id}>{video.name} · #{video.id}</option>)}</select></FormField>
          <FormField label={t('Choose a detection run')}><select value={selectedDetectionRunId} onChange={(event) => setSelectedDetectionRunId(event.target.value)} disabled={runsLoading || detectionRuns.length === 0}><option value="">{t('Select a completed detection run')}</option>{detectionRuns.map((run) => <option key={run.id} value={run.id}>#{run.id} · {run.detections_count} {t('detections')} · {formatDate(run.created_at)}</option>)}</select></FormField>
          <FormField label={t('IoU threshold')} hint={t('Higher values require stronger overlap between consecutive boxes.')}><input type="number" min="0.05" max="0.95" step="0.05" value={iouThreshold} onChange={(event) => setIouThreshold(event.target.value)}/></FormField>
          <FormField label={t('Maximum missing frames')} hint={t('0–30 detector frames')}><input type="number" min="0" max="30" value={maxGapFrames} onChange={(event) => setMaxGapFrames(event.target.value)}/></FormField>
        </div>
        <div className="tracking-setup-footer"><span><GitBranch size={15}/>{t('Class-aware greedy IoU tracker')}</span><Button onClick={() => void startTracking()} disabled={creating || !selectedDetectionRun}>{t(creating ? 'Processing tracking…' : 'Run tracking')}<Crosshair size={16}/></Button></div>
        {!runsLoading && selectedVideoId && detectionRuns.length === 0 && <div className="notice notice-warning">{t('Complete an object-detection run before starting object tracking.')}</div>}
        {error && <div className="notice notice-error">{t(error)}</div>}
      </section>

      <div className="tracking-metrics-grid">
        <Metric label={t('Frames processed')} value={selectedTrackingRun?.frames_processed ?? '—'} icon={<ScanLine size={17}/>}/>
        <Metric label={t('Tracks created')} value={selectedTrackingRun?.tracks_count ?? '—'} icon={<Waypoints size={17}/>}/>
        <Metric label={t('Observed detections')} value={selectedTrackingRun?.observations_count ?? '—'} icon={<Activity size={17}/>}/>
      </div>

      <div className="tracking-content-grid">
        <section className="panel tracking-runs-panel"><SectionHeading title={t('Tracking runs')} subtitle={t('Tracking history for the selected detection run')}/>
          {runsLoading ? <LoadingState label={t('Loading tracking runs…')}/> : trackingRuns.length === 0 ? <EmptyState title={t('No tracking runs')} description={t('Create a tracking run to associate detections across frames.')}/> : <div className="tracking-run-list">{trackingRuns.map((run) => <button type="button" key={run.id} className={`tracking-run-row ${String(run.id) === selectedTrackingRunId ? 'selected' : ''}`} onClick={() => setSelectedTrackingRunId(String(run.id))}><span className="tracking-run-icon"><GitBranch size={16}/></span><span className="tracking-run-main"><strong>{t('Run #')}{run.id}</strong><small>{formatDate(run.created_at)} · IoU {run.iou_threshold.toFixed(2)} · gap {run.max_gap_frames}</small></span><StatusBadge status={run.status}/></button>)}</div>}
          {selectedTrackingRun && ['queued', 'processing'].includes(selectedTrackingRun.status) && <div className="tracking-worker-command"><span>{t('Backend worker command')}</span><code>python manage.py track_video_objects --run-id {selectedTrackingRun.id}</code><small>{t('Run this in the Django backend terminal to process the queued tracking job.')}</small></div>}
          {selectedTrackingRun?.error_message && <div className="notice notice-error">{t(selectedTrackingRun.error_message)}</div>}
        </section>

        <section className="panel tracking-tracks-panel"><SectionHeading title={t('Track inventory')} subtitle={t('Select a track to inspect its observations')}/>
          {tracksLoading ? <LoadingState label={t('Loading tracks…')}/> : !selectedTrackingRun || selectedTrackingRun.status !== 'completed' ? <EmptyState title={t('No tracks available')} description={t('The selected tracking run has not produced tracks yet.')}/> : tracks.length === 0 ? <EmptyState title={t('No tracks available')} description={t('No tracks match the selected class and tracking parameters.')}/> : <div className="track-list">{tracks.map((track) => <button type="button" className={`track-row ${String(track.id) === selectedTrackId ? 'selected' : ''}`} key={track.id} onClick={() => setSelectedTrackId(String(track.id))}><span className="track-number-badge">{track.track_number}</span><span className="track-row-main"><strong>{t(titleCase(track.label))}</strong><small>{t('Frame range')}: {track.first_frame_number}–{track.last_frame_number} · {track.observations_count} {t('Observations')}</small></span><span className="track-row-confidence">#{track.id}</span></button>)}</div>}
        </section>
      </div>

      <section className="panel tracking-detail-panel"><SectionHeading title={t('Track details')} subtitle={t('Inspect the frame-by-frame observations for one object track')}/>
        {!selectedTrack ? <EmptyState title={t('No track selected')} description={t('Select a track to inspect its observations.')}/> : <>
          <div className="track-detail-head"><div className="track-number-badge large">{selectedTrack.track_number}</div><div><h3>{t(titleCase(selectedTrack.label))} · {t('Track #')}{selectedTrack.track_number}</h3><p>{t('First seen')}: {formatDuration(selectedTrack.first_timestamp_seconds)} · {t('Last seen')}: {formatDuration(selectedTrack.last_timestamp_seconds)}</p></div><span className="count-pill">{selectedTrack.observations?.length ?? selectedTrack.observations_count} {t('Observations')}</span></div>
          <div className="tracking-observation-grid">{(selectedTrack.observations || []).map((observation) => <article className="tracking-observation" key={observation.id}><div><strong>{t('Frame ')}{observation.frame_number}</strong><span>{formatDuration(observation.timestamp_seconds)}</span></div><div className="observation-box"><Crosshair size={14}/><code>{observation.bounding_box.map((value) => Math.round(value)).join(', ')}</code></div><div className="observation-confidence"><span>{t('Confidence')}</span><strong>{Math.round(observation.confidence * 100)}%</strong></div></article>)}</div>
        </>}
      </section>
    </>}
  </>;
}

function Metric({ label, value, icon }: { label: string; value: number | string; icon: ReactNode }) {
  return <div className="panel tracking-metric"><div className="tracking-metric-icon">{icon}</div><span>{label}</span><strong>{value}</strong></div>;
}

function ShieldAlertIcon() {
  return <span className="tracking-disclaimer-icon"><Crosshair size={18}/></span>;
}
