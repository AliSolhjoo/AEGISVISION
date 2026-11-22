import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MouseEvent, ReactNode } from 'react';
import {
  Activity, AlertTriangle, Camera, CheckCircle2, Circle, Cpu, Play,
  RefreshCw, ShieldAlert, Square, Wifi, WifiOff, Zap,
} from 'lucide-react';
import { useOrganizations } from '../context/OrganizationContext';
import { api, describeApiError } from '../lib/api';
import type { Camera as CameraType, CameraAnalyticsRule, CameraLiveEvent, CameraLiveState } from '../lib/types';
import { t, useLanguage } from '../i18n';
import { Button, EmptyState, LoadingState, PageHeader } from '../components/Ui';
import StatusBadge from '../components/StatusBadge';
import { notify } from '../components/Toast';

interface WorkerHealth {
  online: boolean;
  process_id: number | null;
  last_heartbeat: string | null;
  total: number;
  online_cameras: number;
  requested_cameras: number;
}

const emptyState = (camera: CameraType): CameraLiveState => ({
  camera_id: camera.id,
  camera_name: camera.name,
  status: 'stopped',
  is_requested: false,
  worker_online: false,
  session_id: '',
  frame_number: 0,
  frames_processed: 0,
  objects_count: 0,
  tracks_count: 0,
  fps_actual: 0,
  width: null,
  height: null,
  latest_detections: [],
  last_error: '',
  session_started_at: null,
  last_frame_at: null,
  last_inference_at: null,
  snapshot_available: false,
  updated_at: null,
});

function statusLabel(status: CameraLiveState['status']) {
  const labels: Record<CameraLiveState['status'], string> = {
    stopped: 'Stopped', starting: 'Starting', online: 'Online',
    reconnecting: 'Reconnecting', error: 'Error',
  };
  return t(labels[status]);
}

function eventTypeLabel(type: string) {
  const labels: Record<string, string> = {
    zone_intrusion: 'Zone intrusion',
    line_crossing: 'Line crossing',
    loitering: 'Loitering',
  };
  return t(labels[type] || type);
}

function timeLabel(value: string | null | undefined, language: string) {
  if (!value) return t('Not reported');
  try {
    return new Intl.DateTimeFormat(language === 'fa' ? 'fa-IR' : 'en-US', {
      hour: '2-digit', minute: '2-digit', second: '2-digit',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

export default function LiveCamerasPage() {
  const { language } = useLanguage();
  const { activeOrganization } = useOrganizations();
  const [cameras, setCameras] = useState<CameraType[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [live, setLive] = useState<CameraLiveState | null>(null);
  const [events, setEvents] = useState<CameraLiveEvent[]>([]);
  const [rules, setRules] = useState<CameraAnalyticsRule[]>([]);
  const [health, setHealth] = useState<WorkerHealth | null>(null);
  const [frameUrl, setFrameUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<'start' | 'stop' | 'test' | null>(null);
  const [error, setError] = useState('');
  const pollingRef = useRef(false);
  const frameUrlRef = useRef('');

  const selectedCamera = useMemo(
    () => cameras.find((camera) => camera.id === selectedId) || null,
    [cameras, selectedId],
  );

  const cameraPath = useCallback((cameraId: number) => {
    if (!activeOrganization) throw new Error('No active organization.');
    return `/api/organizations/${activeOrganization.id}/cameras/${cameraId}`;
  }, [activeOrganization?.id]);

  const loadCameras = useCallback(async () => {
    if (!activeOrganization) {
      setCameras([]);
      setSelectedId(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await api.get<CameraType[]>(`/api/organizations/${activeOrganization.id}/cameras/`);
      setCameras(result);
      setSelectedId((current) => current && result.some((item) => item.id === current)
        ? current
        : (result.find((item) => item.is_enabled && item.source_type !== 'browser')?.id ?? result[0]?.id ?? null));
    } catch (err) {
      setError(describeApiError(err));
    } finally {
      setLoading(false);
    }
  }, [activeOrganization?.id]);

  const loadHealth = useCallback(async () => {
    if (!activeOrganization) return;
    try {
      const data = await api.get<WorkerHealth>(`/api/organizations/${activeOrganization.id}/live-camera-worker/health/`);
      setHealth(data);
    } catch {
      setHealth({ online: false, process_id: null, last_heartbeat: null, total: 0, online_cameras: 0, requested_cameras: 0 });
    }
  }, [activeOrganization?.id]);

  const loadStatus = useCallback(async (camera: CameraType) => {
    try {
      const data = await api.get<CameraLiveState>(`${cameraPath(camera.id)}/live/`);
      setLive(data);
    } catch (err) {
      setError(describeApiError(err));
    }
  }, [cameraPath]);

  const loadEvents = useCallback(async (camera: CameraType) => {
    try {
      setEvents(await api.get<CameraLiveEvent[]>(`${cameraPath(camera.id)}/live/events/`));
    } catch {
      setEvents([]);
    }
  }, [cameraPath]);

  const loadRules = useCallback(async (camera: CameraType) => {
    try {
      setRules(await api.get<CameraAnalyticsRule[]>(`${cameraPath(camera.id)}/event-rules/`));
    } catch {
      setRules([]);
    }
  }, [cameraPath]);

  useEffect(() => { void loadCameras(); }, [loadCameras]);
  useEffect(() => { void loadHealth(); const timer = window.setInterval(() => { if (!document.hidden) void loadHealth(); }, 4000); return () => window.clearInterval(timer); }, [loadHealth]);

  useEffect(() => {
    if (!selectedCamera) {
      setLive(null);
      setEvents([]);
      setRules([]);
      setFrameUrl('');
      return;
    }
    setLive(emptyState(selectedCamera));
    void loadStatus(selectedCamera);
    void loadEvents(selectedCamera);
    void loadRules(selectedCamera);
    const statusTimer = window.setInterval(() => {
      if (!document.hidden && !pollingRef.current) {
        pollingRef.current = true;
        void Promise.all([loadStatus(selectedCamera), loadEvents(selectedCamera), loadRules(selectedCamera)]).finally(() => { pollingRef.current = false; });
      }
    }, 1400);
    return () => window.clearInterval(statusTimer);
  }, [selectedCamera?.id, loadStatus, loadEvents, loadRules]);

  useEffect(() => {
    if (!selectedCamera || !live?.snapshot_available || live.status !== 'online') return;
    let cancelled = false;
    let inFlight = false;
    const refreshFrame = async () => {
      if (cancelled || inFlight || document.hidden) return;
      inFlight = true;
      try {
        const blob = await api.blob(`${cameraPath(selectedCamera.id)}/live/snapshot/?v=${Date.now()}`);
        if (cancelled || !(blob instanceof Blob) || blob.size === 0) return;
        const nextUrl = URL.createObjectURL(blob);
        const oldUrl = frameUrlRef.current;
        frameUrlRef.current = nextUrl;
        setFrameUrl(nextUrl);
        if (oldUrl) URL.revokeObjectURL(oldUrl);
      } catch {
        // A brief missing snapshot while connecting is normal.
      } finally {
        inFlight = false;
      }
    };
    void refreshFrame();
    const timer = window.setInterval(() => { void refreshFrame(); }, 650);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [selectedCamera?.id, live?.snapshot_available, live?.status, cameraPath]);

  useEffect(() => () => {
    if (frameUrlRef.current) URL.revokeObjectURL(frameUrlRef.current);
  }, []);

  const runAction = async (action: 'start' | 'stop' | 'test') => {
    if (!selectedCamera) return;
    setBusy(action);
    setError('');
    try {
      const base = cameraPath(selectedCamera.id);
      if (action === 'start') {
        await api.post(`${base}/live/start/`);
        notify('Live stream requested', selectedCamera.name);
      } else if (action === 'stop') {
        await api.post(`${base}/live/stop/`);
        notify('Live stream stopped', selectedCamera.name);
      } else {
        const result = await api.post<{ ok: boolean; detail: string; width?: number; height?: number; fps?: number }>(`${base}/test-connection/`);
        notify('Camera connection successful', `${result.width} × ${result.height}${result.fps ? ` · ${result.fps} FPS` : ''}`);
      }
      await Promise.all([loadStatus(selectedCamera), loadEvents(selectedCamera), loadHealth()]);
    } catch (err) {
      const message = describeApiError(err);
      setError(message);
      notify(action === 'test' ? 'Camera connection failed' : 'Live camera action failed', message, 'error');
    } finally {
      setBusy(null);
    }
  };

  const updateEventStatus = async (event: CameraLiveEvent, nextStatus: CameraLiveEvent['status']) => {
    if (!selectedCamera) return;
    try {
      await api.patch(`${cameraPath(selectedCamera.id)}/live/events/${event.id}/`, { status: nextStatus });
      await loadEvents(selectedCamera);
    } catch (err) {
      notify('Could not update live event', describeApiError(err), 'error');
    }
  };

  const active = live?.status === 'online';
  const sourceSupported = selectedCamera?.source_type === 'rtsp' || selectedCamera?.source_type === 'rtsps';

  return <>
    <PageHeader
      eyebrow={t('LIVE CAMERA INTELLIGENCE')}
      title={t('Live camera intelligence')}
      description={t('Connect to RTSP cameras, run real-time AI detection and tracking, and review live security events.')}
      actions={<Button variant="secondary" onClick={() => { void loadCameras(); void loadHealth(); }}><RefreshCw size={16}/>{t('Refresh')}</Button>}
    />

    <div className="live-ops-strip">
      <div className={`live-worker-indicator ${health?.online ? 'is-online' : 'is-offline'}`}>
        <span className="pulse-dot"/>
        <div><strong>{health?.online ? t('Live worker online') : t('Live worker offline')}</strong><small>{health?.online ? t('Background engine heartbeat is healthy') : t('Start AEGISVISION with the updated launcher')}</small></div>
      </div>
      <div className="live-ops-count"><strong>{health?.online_cameras ?? 0}</strong><span>{t('Cameras online')}</span></div>
      <div className="live-ops-count"><strong>{health?.requested_cameras ?? 0}</strong><span>{t('Streams requested')}</span></div>
      <div className="live-ops-count"><strong>{cameras.filter((item) => item.is_enabled).length}</strong><span>{t('Enabled cameras')}</span></div>
    </div>

    {loading ? <LoadingState label={t('Loading camera inventory…')}/> : error && !selectedCamera ? <div className="notice notice-error">{t(error)}</div> : cameras.length === 0 ? <EmptyState title={t('No cameras registered')} description={t('Register an RTSP or RTSPS network camera before starting live AI analysis.')}/> : <div className="live-console-grid">
      <aside className="live-camera-rail panel">
        <div className="live-rail-heading"><div><span className="live-section-kicker">{t('CAMERA SOURCES')}</span><h2>{t('Camera inventory')}</h2></div><span className="count-pill">{cameras.length}</span></div>
        <div className="live-camera-list">
          {cameras.map((camera) => {
            const isSelected = camera.id === selectedId;
            return <button key={camera.id} className={`live-camera-option ${isSelected ? 'selected' : ''}`} onClick={() => setSelectedId(camera.id)}>
              <span className={`live-camera-option-icon ${camera.status === 'online' ? 'online' : ''}`}><Camera size={17}/></span>
              <span className="live-camera-option-copy"><strong>{camera.name}</strong><small>{camera.location || camera.code}</small></span>
              <span className={`live-camera-status-dot ${camera.status === 'online' ? 'online' : camera.status === 'error' ? 'error' : ''}`}/>
            </button>;
          })}
        </div>
      </aside>

      <section className="live-main-column">
        {selectedCamera && live && <>
          <div className="live-viewer-panel panel">
            <div className="live-viewer-toolbar">
              <div className="live-viewer-title"><span className="live-section-kicker">{t('LIVE FEED')}</span><h2>{selectedCamera.name}</h2><small>{selectedCamera.location || selectedCamera.code}</small></div>
              <div className="live-viewer-actions">
                <StatusBadge status={live.status}/>
                <Button variant="secondary" size="small" onClick={() => void runAction('test')} disabled={busy !== null || selectedCamera.source_type === 'browser'}><Wifi size={15}/>{t('Test connection')}</Button>
                {!live.is_requested && <Button size="small" onClick={() => void runAction('start')} disabled={busy !== null || !selectedCamera.is_enabled || !sourceSupported || !health?.online}><Play size={15}/>{t(busy === 'start' ? 'Starting…' : 'Start live')}</Button>}
                {live.is_requested && <Button variant="danger" size="small" onClick={() => void runAction('stop')} disabled={busy !== null}><Square size={14}/>{t(busy === 'stop' ? 'Stopping…' : 'Stop live')}</Button>}
              </div>
            </div>

            <div className={`live-video-stage ${active ? 'is-live' : ''}`}>
              {frameUrl && active ? <img src={frameUrl} alt={t('Live camera frame with AI detections and tracking IDs')} className="live-frame-image"/> : <div className="live-video-placeholder">
                {live.status === 'starting' || live.status === 'reconnecting' ? <><RefreshCw className="live-placeholder-spin" size={32}/><strong>{t(live.status === 'starting' ? 'Connecting to camera…' : 'Reconnecting to camera…')}</strong><span>{t('The worker is opening the RTSP stream and waiting for the first frame.')}</span></> : live.status === 'error' ? <><AlertTriangle size={34}/><strong>{t('Live camera error')}</strong><span>{t(live.last_error || 'Check the camera stream settings and network connection.')}</span></> : <><Camera size={38}/><strong>{t('Live feed is stopped')}</strong><span>{t('Select Start live to connect and begin real-time AI analysis.')}</span></>}
              </div>}
              <div className="live-stage-badges"><span className={`live-stage-state ${active ? 'online' : ''}`}><span className="pulse-dot"/>{statusLabel(live.status)}</span>{active && <span>{t('AI OVERLAY')}</span>}</div>
            </div>

            {live.last_error && <div className="notice notice-error live-error-notice"><AlertTriangle size={16}/>{t(live.last_error)}</div>}
            {!health?.online && <div className="notice notice-warning live-error-notice"><WifiOff size={16}/><span>{t('The live worker is not running. Close the old launcher and start the updated Start_AEGISVISION.bat file.')}</span></div>}
            {!sourceSupported && <div className="notice notice-info live-error-notice">{t('Browser camera sources are not supported by the server-side RTSP worker. Register an RTSP or RTSPS camera for live AI processing.')}</div>}
          </div>

          <div className="live-metrics-grid">
            <LiveMetric icon={<Activity size={17}/>} label={t('Inference FPS')} value={active ? live.fps_actual.toFixed(1) : '—'} detail={t('AI sampled frames per second')}/>
            <LiveMetric icon={<Zap size={17}/>} label={t('Objects in frame')} value={active ? live.objects_count : '—'} detail={t('Current frame detections')}/>
            <LiveMetric icon={<Cpu size={17}/>} label={t('Active tracks')} value={active ? live.tracks_count : '—'} detail={t('SORT track IDs in current frame')}/>
            <LiveMetric icon={<CheckCircle2 size={17}/>} label={t('Frames analyzed')} value={live.frames_processed} detail={t('Frames processed this session')}/>
          </div>

          <div className="panel live-detections-panel">
            <div className="live-panel-heading"><div><span className="live-section-kicker">{t('CURRENT FRAME')}</span><h2>{t('Detected objects')}</h2></div><span className="count-pill">{live.latest_detections.length}</span></div>
            {live.latest_detections.length ? <div className="live-detection-chips">{live.latest_detections.map((item, index) => <div key={`${item.track_number}-${index}`} className="live-detection-chip"><span className="live-detection-dot"/><strong>{t(item.label)}</strong><span>#{item.track_number}</span><small>{Math.round(item.confidence * 100)}%</small></div>)}</div> : <div className="live-no-detections"><Circle size={14}/>{t(active ? 'No objects passed the confidence threshold in the latest frame.' : 'No live detections are available.')}</div>}
          </div>
        </>}
      </section>

      <aside className="live-side-column">
        {selectedCamera && live && <>
          <section className="panel live-details-panel">
            <div className="live-panel-heading"><div><span className="live-section-kicker">{t('STREAM DIAGNOSTICS')}</span><h2>{t('Connection details')}</h2></div><Activity size={17}/></div>
            <div className="live-detail-row"><span>{t('Source type')}</span><strong>{selectedCamera.source_type.toUpperCase()}</strong></div>
            <div className="live-detail-row"><span>{t('Configured inference')}</span><strong>{selectedCamera.target_fps} FPS</strong></div>
            <div className="live-detail-row"><span>{t('Confidence threshold')}</span><strong>{Math.round(selectedCamera.confidence_threshold * 100)}%</strong></div>
            <div className="live-detail-row"><span>{t('Resolution')}</span><strong>{live.width && live.height ? `${live.width} × ${live.height}` : '—'}</strong></div>
            <div className="live-detail-row"><span>{t('Last frame')}</span><strong>{timeLabel(live.last_frame_at, language)}</strong></div>
            <div className="live-detail-row"><span>{t('Session started')}</span><strong>{timeLabel(live.session_started_at, language)}</strong></div>
            <div className="live-detail-row"><span>{t('Credentials')}</span><strong>{selectedCamera.has_stream_credentials ? t('Encrypted') : t('Not configured')}</strong></div>
          </section>

          <LiveRulesPanel
            camera={selectedCamera}
            organizationId={activeOrganization?.id || ''}
            active={active}
            frameUrl={frameUrl}
            frameAspectRatio={live.width && live.height ? `${live.width} / ${live.height}` : '16 / 9'}
            rules={rules}
            onReload={() => void loadRules(selectedCamera)}
          />

          <section className="panel live-events-panel">
            <div className="live-panel-heading"><div><span className="live-section-kicker">{t('REAL-TIME ALERTS')}</span><h2>{t('Live security events')}</h2></div><span className="count-pill">{events.filter((event) => !['resolved', 'false_positive'].includes(event.status)).length}</span></div>
            {events.length ? <div className="live-event-list">{events.slice(0, 12).map((event) => <article className="live-event-item" key={event.id}>
              <span className={`live-event-symbol severity-${event.severity}`}><ShieldAlert size={16}/></span>
              <div className="live-event-copy"><strong>{event.rule_name}</strong><small>{eventTypeLabel(event.event_type)} · {t(event.label)} #{event.track_number}</small><small>{timeLabel(event.occurred_at, language)}</small>
                <div className="live-event-actions">{event.status === 'new' && <button onClick={() => void updateEventStatus(event, 'acknowledged')}>{t('Acknowledge')}</button>}{!['resolved', 'false_positive'].includes(event.status) && <button onClick={() => void updateEventStatus(event, 'resolved')}>{t('Resolve')}</button>}<span>{t(event.status.replace('_', ' '))}</span></div>
              </div>
            </article>)}</div> : <div className="live-no-detections"><CheckCircle2 size={15}/>{t('No live security events have been recorded for this camera.')}</div>}
          </section>
        </>}
      </aside>
    </div>}
    {error && selectedCamera && <div className="notice notice-error live-global-error">{t(error)}</div>}
  </>;
}

function LiveMetric({ icon, label, value, detail }: { icon: ReactNode; label: string; value: string | number; detail: string }) {
  return <div className="live-metric-card panel"><div className="live-metric-icon">{icon}</div><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></div>;
}


type LiveRuleType = CameraAnalyticsRule['rule_type'];

function LiveRulesPanel({
  camera,
  organizationId,
  active,
  frameUrl,
  frameAspectRatio,
  rules,
  onReload,
}: {
  camera: CameraType;
  organizationId: string;
  active: boolean;
  frameUrl: string;
  frameAspectRatio: string;
  rules: CameraAnalyticsRule[];
  onReload: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [drawing, setDrawing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [name, setName] = useState('');
  const [ruleType, setRuleType] = useState<LiveRuleType>('zone_intrusion');
  const [labels, setLabels] = useState('person');
  const [confidence, setConfidence] = useState(0.55);
  const [dwell, setDwell] = useState(10);
  const [direction, setDirection] = useState<'both' | 'negative_to_positive' | 'positive_to_negative'>('both');
  const [points, setPoints] = useState<number[][]>([]);
  const [ruleError, setRuleError] = useState('');
  const path = `/api/organizations/${organizationId}/cameras/${camera.id}/event-rules/`;

  const resetDraft = () => {
    setName(''); setRuleType('zone_intrusion'); setLabels('person'); setConfidence(0.55);
    setDwell(10); setDirection('both'); setPoints([]); setDrawing(false); setRuleError('');
  };

  const onOverlayClick = (event: MouseEvent<SVGSVGElement>) => {
    if (!drawing || !active) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const point = [
      Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)),
      Math.max(0, Math.min(1, (event.clientY - rect.top) / rect.height)),
    ];
    setPoints((current) => {
      if (ruleType === 'line_crossing') return current.length >= 2 ? current : [...current, point];
      return [...current, point];
    });
  };

  const requiredPoints = ruleType === 'line_crossing' ? 2 : 3;
  const canSave = name.trim().length > 0 && points.length >= requiredPoints && (!active || frameUrl.length > 0);

  const saveRule = async () => {
    if (!canSave || saving) return;
    setSaving(true); setRuleError('');
    const cleanLabels = labels.split(',').map((item) => item.trim().toLowerCase()).filter(Boolean);
    const geometry = ruleType === 'line_crossing' ? { line: points.slice(0, 2) } : { polygon: points };
    try {
      await api.post(path, {
        name: name.trim(),
        scope: 'camera',
        rule_type: ruleType,
        geometry,
        labels: cleanLabels,
        minimum_confidence: confidence,
        anchor: 'bottom_center',
        direction,
        dwell_seconds: dwell,
        is_active: true,
      });
      notify('Camera rule created', name.trim());
      resetDraft();
      setExpanded(false);
      onReload();
    } catch (err) {
      const message = describeApiError(err);
      setRuleError(message);
    } finally {
      setSaving(false);
    }
  };

  const toggleRule = async (rule: CameraAnalyticsRule) => {
    try {
      await api.patch(`${path}${rule.id}/`, { is_active: !rule.is_active });
      onReload();
    } catch (err) {
      notify('Could not update camera rule', describeApiError(err), 'error');
    }
  };

  const deleteRule = async (rule: CameraAnalyticsRule) => {
    if (!window.confirm(t('Delete this camera rule?'))) return;
    try {
      await api.delete(`${path}${rule.id}/`);
      onReload();
    } catch (err) {
      notify('Could not delete camera rule', describeApiError(err), 'error');
    }
  };

  return <section className="panel live-rules-panel">
    <div className="live-panel-heading">
      <div><span className="live-section-kicker">{t('CAMERA ANALYTICS')}</span><h2>{t('Live analytics rules')}</h2></div>
      <span className="count-pill">{rules.length}</span>
    </div>
    <div className="live-rule-list">
      {rules.map((rule) => <div className="live-rule-item" key={rule.id}>
        <div className={`live-rule-type-icon rule-${rule.rule_type}`}><ShieldAlert size={14}/></div>
        <div className="live-rule-copy"><strong>{rule.name}</strong><small>{eventTypeLabel(rule.rule_type)} · {rule.labels.length ? rule.labels.join(', ') : t('All object classes')}</small></div>
        <button className={`live-rule-toggle ${rule.is_active ? 'active' : ''}`} onClick={() => void toggleRule(rule)} title={t(rule.is_active ? 'Disable rule' : 'Enable rule')} aria-pressed={rule.is_active}><span/></button>
        <button className="icon-button danger-icon" onClick={() => void deleteRule(rule)} title={t('Delete rule')}><Square size={13}/></button>
      </div>)}
      {!rules.length && <div className="live-no-detections"><ShieldAlert size={14}/>{t('No rules configured for this camera yet.')}</div>}
    </div>
    {!expanded ? <div className="live-rule-add-row"><button className="button button-secondary button-small" disabled={!active || !frameUrl} onClick={() => { resetDraft(); setExpanded(true); }}><Zap size={14}/>{t('Create camera rule')}</button><small>{t('Rules are applied automatically by the live worker.')}</small></div> : <div className="live-rule-editor">
      <div className="live-rule-editor-head"><strong>{t('New camera rule')}</strong><button className="icon-button" onClick={() => { setExpanded(false); resetDraft(); }} title={t('Cancel')}>×</button></div>
      <label className="live-rule-field"><span>{t('Rule name')}</span><input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} placeholder={t('North gate restricted zone')}/></label>
      <div className="live-rule-form-grid">
        <label className="live-rule-field"><span>{t('Rule type')}</span><select value={ruleType} onChange={(event) => { setRuleType(event.target.value as LiveRuleType); setPoints([]); setDrawing(false); }}><option value="zone_intrusion">{t('Zone intrusion')}</option><option value="line_crossing">{t('Line crossing')}</option><option value="loitering">{t('Loitering')}</option></select></label>
        <label className="live-rule-field"><span>{t('Minimum confidence')}</span><select value={confidence} onChange={(event) => setConfidence(Number(event.target.value))}>{[0.35,0.45,0.55,0.65,0.75,0.85].map((value) => <option key={value} value={value}>{Math.round(value * 100)}%</option>)}</select></label>
      </div>
      <label className="live-rule-field"><span>{t('Object labels')}</span><input value={labels} onChange={(event) => setLabels(event.target.value)} placeholder="person, car"/><small>{t('Comma-separated COCO labels. Leave blank to include all objects.')}</small></label>
      {ruleType === 'loitering' && <label className="live-rule-field"><span>{t('Dwell threshold (seconds)')}</span><input type="number" min={1} max={86400} value={dwell} onChange={(event) => setDwell(Math.max(1, Number(event.target.value) || 1))}/></label>}
      {ruleType === 'line_crossing' && <label className="live-rule-field"><span>{t('Crossing direction')}</span><select value={direction} onChange={(event) => setDirection(event.target.value as typeof direction)}><option value="both">{t('Both directions')}</option><option value="negative_to_positive">{t('Negative to positive')}</option><option value="positive_to_negative">{t('Positive to negative')}</option></select></label>}
      <div className="live-rule-draw-toolbar"><span>{t(ruleType === 'line_crossing' ? 'Click two points to draw a virtual line.' : 'Click at least three points to draw a restricted area.')}</span><div><button onClick={() => setPoints((current) => current.slice(0, -1))} disabled={!points.length}>{t('Undo point')}</button><button onClick={() => setPoints([])} disabled={!points.length}>{t('Clear points')}</button></div></div>
      <div className="live-rule-editor-stage" style={{ aspectRatio: frameAspectRatio }}>
        {frameUrl ? <img src={frameUrl} alt={t('Live camera preview for drawing a rule')} draggable={false}/> : <div className="live-rule-no-frame">{t('Start the live stream to draw rule geometry on the camera image.')}</div>}
        <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" onClick={onOverlayClick} className={drawing ? 'is-drawing' : ''}>
          {rules.map((rule) => {
            const polygon = rule.geometry.polygon || [];
            const line = rule.geometry.line || [];
            return <g key={rule.id} className={rule.is_active ? 'saved-rule-active' : 'saved-rule-inactive'}>
              {polygon.length >= 3 && <polygon points={polygon.map((point) => `${point[0]*1000},${point[1]*1000}`).join(' ')} />}
              {line.length === 2 && <line x1={line[0][0]*1000} y1={line[0][1]*1000} x2={line[1][0]*1000} y2={line[1][1]*1000}/>}
            </g>;
          })}
          {points.length > 0 && <>
            {ruleType !== 'line_crossing' && points.length >= 3 && <polygon className="pending-rule-shape" points={points.map((point) => `${point[0]*1000},${point[1]*1000}`).join(' ')}/>}
            {points.length >= 2 && ruleType === 'line_crossing' && <line className="pending-rule-shape" x1={points[0][0]*1000} y1={points[0][1]*1000} x2={points[1][0]*1000} y2={points[1][1]*1000}/>}
            {points.map((point, index) => <circle key={index} className="pending-rule-point" cx={point[0]*1000} cy={point[1]*1000} r="10"/>)}
          </>}
        </svg>
      </div>
      <div className="live-rule-draw-footer"><span>{t('Geometry points')}: {points.length} / {requiredPoints}{ruleType !== 'line_crossing' && points.length > requiredPoints ? '+' : ''}</span><button className="button button-secondary button-small" onClick={() => setDrawing((current) => !current)} disabled={!active || !frameUrl}>{drawing ? t('Finish drawing') : t('Draw on live frame')}</button></div>
      {ruleError && <div className="notice notice-error">{t(ruleError)}</div>}
      <div className="live-rule-editor-actions"><button className="button button-ghost button-small" onClick={() => { resetDraft(); setExpanded(false); }}>{t('Cancel')}</button><button className="button button-primary button-small" disabled={!canSave || saving} onClick={() => void saveRule()}>{t(saving ? 'Saving…' : 'Save camera rule')}</button></div>
      {!active && <div className="live-rule-help-note">{t('Connect the camera before drawing a rule.')}</div>}
    </div>}
  </section>;
}

