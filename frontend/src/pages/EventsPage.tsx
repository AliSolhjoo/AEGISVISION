import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  Activity, AlertTriangle, BellRing, Check, CheckCircle2, Clock3, Crosshair,
  Film, Loader2, Minus, Pause, Play, Plus, RefreshCw, ShieldAlert,
  Trash2, Undo2, XCircle,
} from 'lucide-react';
import { PageHeader } from '../components/Ui';
import { useOrganizations } from '../context/OrganizationContext';
import { api, describeApiError } from '../lib/api';
import type { VideoAsset } from '../lib/types';
import { useLanguage } from '../i18n';

type RuleType = 'zone_intrusion' | 'line_crossing' | 'loitering';
type EventStatus = 'new' | 'acknowledged' | 'investigating' | 'resolved' | 'false_positive';

type AnalyticsRule = {
  id: number;
  asset_id: number | null;
  camera_id: number | null;
  scope: 'asset' | 'camera';
  name: string;
  rule_type: RuleType;
  geometry: { polygon?: number[][]; line?: number[][] };
  labels: string[];
  minimum_confidence: number;
  anchor: 'bottom_center' | 'center';
  direction: 'both' | 'negative_to_positive' | 'positive_to_negative';
  dwell_seconds: number;
  is_active: boolean;
};

type SecurityEvent = {
  id: number;
  asset_id: number;
  asset_name: string;
  tracking_run_id: number;
  rule_id: number | null;
  rule_name: string;
  event_type: RuleType;
  track_number: number;
  label: string;
  timestamp_seconds: number;
  frame_number: number;
  confidence: number;
  details: Record<string, unknown>;
  status: EventStatus;
  created_at: string;
};

type WorkspaceState = {
  asset_id: number;
  tracking_ready: boolean;
  tracking_run_id: number | null;
  tracking_run_status: string | null;
  active_rules_count: number;
  events_count: number;
};

type AnalyzeResponse = {
  tracking_run_id: number;
  event_summary: { total_events: number; events_by_type: Record<string, number>; events_by_rule: Record<string, number> };
  summary: { unique_tracks: number; total_observations: number; tracks_by_label: Record<string, number> };
  persistence: { created: number; updated: number; total: number };
};

const eventColors = ['#fb7185', '#38bdf8', '#a78bfa', '#fbbf24', '#34d399', '#f97316'];
const formatTime = (seconds: number) => {
  const safe = Math.max(0, Number(seconds) || 0);
  const minutes = Math.floor(safe / 60);
  const remaining = (safe % 60).toFixed(1).padStart(4, '0');
  return `${String(minutes).padStart(2, '0')}:${remaining}`;
};

export default function EventsPage() {
  const { activeOrganization } = useOrganizations();
  const [searchParams] = useSearchParams();
  const queryAssetId = useMemo(() => {
    const value = Number(searchParams.get('video_id'));
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  }, [searchParams]);
  const { language, direction: siteDirection } = useLanguage();
  const fa = language === 'fa';
  const tr = (persian: string, english: string) => fa ? persian : english;
  const [videos, setVideos] = useState<VideoAsset[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<number | null>(null);
  const [rules, setRules] = useState<AnalyticsRule[]>([]);
  const [events, setEvents] = useState<SecurityEvent[]>([]);
  const [workspace, setWorkspace] = useState<WorkspaceState | null>(null);
  const [loading, setLoading] = useState(false);
  const [savingRule, setSavingRule] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [videoReady, setVideoReady] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [drawingMode, setDrawingMode] = useState(false);
  const [draftPoints, setDraftPoints] = useState<number[][]>([]);
  const [ruleType, setRuleType] = useState<RuleType>('zone_intrusion');
  const [ruleName, setRuleName] = useState(fa ? 'محدوده ممنوعه' : 'Restricted area');
  useEffect(() => {
    setRuleName((current) => {
      if (current === 'محدوده ممنوعه' || current === 'Restricted area') {
        return fa ? 'محدوده ممنوعه' : 'Restricted area';
      }
      return current;
    });
  }, [fa]);
  const [ruleScope, setRuleScope] = useState<'asset' | 'camera'>('asset');
  const [labelsText, setLabelsText] = useState('person, car');
  const [minimumConfidence, setMinimumConfidence] = useState('0.55');
  const [dwellSeconds, setDwellSeconds] = useState('10');
  const [direction, setDirection] = useState<'both' | 'negative_to_positive' | 'positive_to_negative'>('both');
  const [anchor, setAnchor] = useState<'bottom_center' | 'center'>('bottom_center');
  const [eventFilter, setEventFilter] = useState<'all' | EventStatus>('all');
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const videoUrlRef = useRef('');

  const selectedVideo = useMemo(
    () => videos.find((item) => item.id === selectedAssetId) || null,
    [videos, selectedAssetId],
  );

  const loadVideos = useCallback(async () => {
    if (!activeOrganization) {
      setVideos([]);
      setSelectedAssetId(null);
      return;
    }
    const items = await api.get<VideoAsset[]>(`/api/organizations/${activeOrganization.id}/videos/`);
    setVideos(items);
    setSelectedAssetId((current) => queryAssetId && items.some((item) => item.id === queryAssetId)
      ? queryAssetId
      : current && items.some((item) => item.id === current)
        ? current
        : (items.find((item) => item.status === 'completed')?.id ?? items[0]?.id ?? null));
  }, [activeOrganization?.id, queryAssetId]);

  const loadRulesAndEvents = useCallback(async (assetId: number) => {
    if (!activeOrganization) return;
    const base = `/api/organizations/${activeOrganization.id}`;
    const [ruleItems, eventItems, workspaceInfo] = await Promise.all([
      api.get<AnalyticsRule[]>(`${base}/videos/${assetId}/event-rules/`),
      api.get<SecurityEvent[]>(`${base}/events/?video_id=${assetId}&limit=300`),
      api.get<WorkspaceState>(`${base}/videos/${assetId}/event-analysis/`),
    ]);
    setRules(ruleItems);
    setEvents(eventItems);
    setWorkspace(workspaceInfo);
  }, [activeOrganization?.id]);

  useEffect(() => {
    if (!activeOrganization) return;
    setLoading(true);
    setError('');
    loadVideos().catch((reason: unknown) => setError(describeApiError(reason))).finally(() => setLoading(false));
  }, [activeOrganization?.id, loadVideos]);

  useEffect(() => {
    if (!selectedAssetId || !activeOrganization) {
      setRules([]);
      setEvents([]);
      setWorkspace(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError('');
    setVideoReady(false);
    setDuration(0);
    setCurrentTime(0);
    setSelectedEventId(null);
    setDraftPoints([]);
    setRuleScope('asset');
    setVideoUrl('');
    const oldUrl = videoUrlRef.current;
    videoUrlRef.current = '';
    if (oldUrl) URL.revokeObjectURL(oldUrl);

    Promise.all([
      loadRulesAndEvents(selectedAssetId),
      api.blob(`/api/video-analysis/assets/${selectedAssetId}/result/`),
    ]).then(([, blob]) => {
      if (cancelled) return;
      const url = URL.createObjectURL(blob);
      videoUrlRef.current = url;
      setVideoUrl(url);
    }).catch((reason: unknown) => {
      if (!cancelled) {
        setError(describeApiError(reason));
      }
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });

    return () => { cancelled = true; };
  }, [selectedAssetId, activeOrganization?.id, loadRulesAndEvents]);

  useEffect(() => () => {
    if (videoUrlRef.current) URL.revokeObjectURL(videoUrlRef.current);
  }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    const video = videoRef.current;
    if (!canvas || !video || !videoReady || !video.videoWidth || !video.videoHeight) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext('2d');
    if (!context) return;
    context.clearRect(0, 0, canvas.width, canvas.height);

    rules.forEach((rule, index) => {
      const color = eventColors[index % eventColors.length];
      const points = rule.geometry.polygon || rule.geometry.line || [];
      if (points.length < 2) return;
      context.save();
      context.strokeStyle = color;
      context.fillStyle = `${color}28`;
      context.lineWidth = Math.max(2, canvas.width / 500);
      context.setLineDash(rule.rule_type === 'line_crossing' ? [12, 8] : []);
      context.beginPath();
      context.moveTo(points[0][0] * canvas.width, points[0][1] * canvas.height);
      points.slice(1).forEach((point) => context.lineTo(point[0] * canvas.width, point[1] * canvas.height));
      if (rule.geometry.polygon) {
        context.closePath();
        context.fill();
      }
      context.stroke();
      context.restore();
    });

    if (draftPoints.length) {
      context.save();
      context.strokeStyle = '#facc15';
      context.fillStyle = 'rgba(250,204,21,.15)';
      context.lineWidth = Math.max(2, canvas.width / 420);
      context.setLineDash([10, 7]);
      context.beginPath();
      context.moveTo(draftPoints[0][0] * canvas.width, draftPoints[0][1] * canvas.height);
      draftPoints.slice(1).forEach((point) => context.lineTo(point[0] * canvas.width, point[1] * canvas.height));
      if (ruleType !== 'line_crossing' && draftPoints.length >= 3) {
        context.closePath();
        context.fill();
      }
      context.stroke();
      draftPoints.forEach((point) => {
        context.beginPath();
        context.arc(point[0] * canvas.width, point[1] * canvas.height, Math.max(4, canvas.width / 160), 0, Math.PI * 2);
        context.fillStyle = '#fde047';
        context.fill();
      });
      context.restore();
    }
  }, [rules, draftPoints, ruleType, videoReady]);

  const visibleEvents = useMemo(() => eventFilter === 'all'
    ? events
    : events.filter((item) => item.status === eventFilter), [events, eventFilter]);
  const statusCounts = useMemo(() => ({
    new: events.filter((item) => item.status === 'new').length,
    acknowledged: events.filter((item) => item.status === 'acknowledged').length,
    resolved: events.filter((item) => item.status === 'resolved').length,
    false_positive: events.filter((item) => item.status === 'false_positive').length,
  }), [events]);

  function handleCanvasClick(event: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawingMode || !canvasRef.current) return;
    const rect = canvasRef.current.getBoundingClientRect();
    const x = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height));
    setDraftPoints((current) => {
      if (ruleType === 'line_crossing' && current.length >= 2) return [[x, y]];
      return [...current, [x, y]];
    });
  }

  async function saveRule() {
    if (!activeOrganization || !selectedAssetId) return;
    const required = ruleType === 'line_crossing' ? 2 : 3;
    if (draftPoints.length < required) {
      setError(tr(`برای این قانون حداقل ${required} نقطه روی تصویر مشخص کن.`, `Mark at least ${required} points on the video for this rule.`));
      return;
    }
    setError('');
    setNotice('');
    const labels = labelsText.split(',').map((value) => value.trim().toLowerCase()).filter(Boolean);
    if (ruleScope === 'camera' && !selectedVideo?.camera_id) {
      setError(tr('این ویدئو به دوربین متصل نیست؛ محدوده ذخیره‌سازی را روی خود ویدئو قرار بده.', 'This video is not linked to a camera. Save the rule to this video instead.'));
      return;
    }
    setSavingRule(true);
    const payload = {
      name: ruleName.trim(),
      rule_type: ruleType,
      geometry: ruleType === 'line_crossing' ? { line: draftPoints } : { polygon: draftPoints },
      labels,
      minimum_confidence: Number(minimumConfidence),
      anchor,
      direction,
      dwell_seconds: Number(dwellSeconds),
      is_active: true,
      scope: ruleScope,
    };
    try {
      await api.post<AnalyticsRule>(`/api/organizations/${activeOrganization.id}/videos/${selectedAssetId}/event-rules/`, payload);
      setDraftPoints([]);
      setDrawingMode(false);
      if (workspace?.tracking_ready) {
        setAnalyzing(true);
        try {
          const report = await api.post<AnalyzeResponse>(`/api/organizations/${activeOrganization.id}/videos/${selectedAssetId}/event-analysis/`, {});
          setNotice(tr(
            `قانون ذخیره شد و تحلیل انجام شد؛ ${report.event_summary.total_events} رویداد پیدا شد.`,
            `Rule saved and evaluated; ${report.event_summary.total_events} events found.`,
          ));
        } catch (reason) {
          setError(describeApiError(reason));
          setNotice(tr('قانون ذخیره شد، اما اجرای تحلیل رویدادها ناموفق بود.', 'Rule saved, but event evaluation failed.'));
        } finally {
          setAnalyzing(false);
        }
      } else {
        setNotice(tr('قانون امنیتی ذخیره شد؛ پس از تکمیل Tracking اجرا می‌شود.', 'Security rule saved; it will run after tracking completes.'));
      }
      await loadRulesAndEvents(selectedAssetId);
    } catch (reason) {
      setError(describeApiError(reason));
    } finally {
      setSavingRule(false);
    }
  }

  async function deleteRule(ruleId: number) {
    if (!activeOrganization || !selectedAssetId) return;
    if (!window.confirm(tr('این قانون حذف شود؟ رویدادهای ثبت‌شده قبلی حفظ می‌شوند.', 'Delete this rule? Previously recorded events will be retained.'))) return;
    try {
      await api.delete(`/api/organizations/${activeOrganization.id}/videos/${selectedAssetId}/event-rules/${ruleId}/`);
      await loadRulesAndEvents(selectedAssetId);
    } catch (reason) {
      setError(describeApiError(reason));
    }
  }

  async function analyzeEvents() {
    if (!activeOrganization || !selectedAssetId) return;
    setAnalyzing(true);
    setError('');
    setNotice('');
    try {
      const report = await api.post<AnalyzeResponse>(`/api/organizations/${activeOrganization.id}/videos/${selectedAssetId}/event-analysis/`, {});
      setNotice(tr(
        `تحلیل رویدادها کامل شد؛ ${report.event_summary.total_events} رویداد شناسایی شد.`,
        `Event analysis completed; ${report.event_summary.total_events} events detected.`,
      ));
      await loadRulesAndEvents(selectedAssetId);
    } catch (reason) {
      setError(describeApiError(reason));
    } finally {
      setAnalyzing(false);
    }
  }

  async function updateEventStatus(item: SecurityEvent, status: EventStatus) {
    if (!activeOrganization) return;
    try {
      const updated = await api.patch<SecurityEvent>(`/api/organizations/${activeOrganization.id}/events/${item.id}/`, { status });
      setEvents((current) => current.map((event) => event.id === item.id ? updated : event));
    } catch (reason) {
      setError(describeApiError(reason));
    }
  }

  function seekToEvent(item: SecurityEvent) {
    const video = videoRef.current;
    if (!video) return;
    video.pause();
    video.currentTime = Math.max(0, item.timestamp_seconds);
    setCurrentTime(Math.max(0, item.timestamp_seconds));
    setPlaying(false);
    setSelectedEventId(item.id);
  }

  function togglePlayback() {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
      void video.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    } else {
      video.pause();
      setPlaying(false);
    }
  }

  const ruleTypeLabel = (type: RuleType) => ({
    zone_intrusion: tr('ورود به محدوده', 'Zone intrusion'),
    line_crossing: tr('عبور از خط', 'Line crossing'),
    loitering: tr('توقف طولانی', 'Loitering'),
  })[type];
  const eventStatusLabel = (status: EventStatus) => ({
    new: tr('جدید', 'New'),
    acknowledged: tr('تأییدشده', 'Acknowledged'),
    investigating: tr('در حال بررسی', 'Investigating'),
    resolved: tr('رسیدگی‌شده', 'Resolved'),
    false_positive: tr('خطای تشخیص', 'False positive'),
  })[status];

  return (
    <div className="event-intelligence-page" dir={siteDirection}>
      <PageHeader
        eyebrow={tr('هوشمندی امنیتی / موتور رویداد', 'SECURITY INTELLIGENCE / EVENT ENGINE')}
        title={tr('رویدادها و قوانین امنیتی', 'Events & Security Rules')}
        description={tr('روی ویدئو محدوده و خط مجازی بکش، قوانین را ذخیره کن و رویدادهای واقعی را از مسیر حرکت اشیا استخراج کن.', 'Draw zones and virtual lines on video, save rules, and evaluate real events from tracked object movement.')}
      />

      {error && <div className="event-alert event-alert-error"><XCircle size={17}/><span>{error}</span><button type="button" onClick={() => setError('')}>×</button></div>}
      {notice && <div className="event-alert event-alert-success"><CheckCircle2 size={17}/><span>{notice}</span><button type="button" onClick={() => setNotice('')}>×</button></div>}

      <section className="event-workspace-grid">
        <div className="panel event-panel event-video-panel">
          <div className="event-panel-heading">
            <div><span className="eyebrow">{tr('شواهد ویدئویی', 'VIDEO EVIDENCE')}</span><h2>{tr('انتخاب و تنظیم تصویر', 'Select & Configure Video')}</h2></div>
            <Film size={20}/>
          </div>
          <label className="event-field">
            {tr('ویدئوی تحلیل‌شده', 'Analyzed video')}
            <select value={selectedAssetId ?? ''} onChange={(event) => setSelectedAssetId(event.target.value ? Number(event.target.value) : null)}>
              <option value="">{tr('انتخاب ویدئو', 'Select a video')}</option>
              {videos.map((video) => <option key={video.id} value={video.id}>{video.name} · #{video.id}</option>)}
            </select>
          </label>
          {selectedVideo && <div className="event-video-meta"><strong>{selectedVideo.name}</strong><span>{selectedVideo.width && selectedVideo.height ? `${selectedVideo.width} × ${selectedVideo.height}` : ''} {selectedVideo.duration_seconds ? `· ${selectedVideo.duration_seconds.toFixed(1)}s` : ''}</span></div>}

          {videoUrl ? (
            <>
              <div className={`event-video-stage ${drawingMode ? 'is-drawing' : ''}`} style={{ aspectRatio: selectedVideo?.width && selectedVideo?.height ? `${selectedVideo.width} / ${selectedVideo.height}` : '16 / 9' }}>
                <video
                  ref={videoRef}
                  src={videoUrl}
                  playsInline
                  preload="metadata"
                  onLoadedMetadata={(event) => {
                    setVideoReady(true);
                    setDuration(event.currentTarget.duration || 0);
                    setCurrentTime(0);
                  }}
                  onTimeUpdate={(event) => setCurrentTime(event.currentTarget.currentTime)}
                  onPlay={() => setPlaying(true)}
                  onPause={() => setPlaying(false)}
                />
                <canvas
                  ref={canvasRef}
                  className="event-drawing-canvas"
                  onClick={handleCanvasClick}
                  style={{ pointerEvents: drawingMode ? 'auto' : 'none' }}
                />
                {!videoReady && <div className="event-video-loading"><Loader2 className="spin" size={22}/>{tr('در حال آماده‌سازی ویدئو…', 'Preparing video…')}</div>}
              </div>
              <div className="event-player-controls">
                <button type="button" className="event-icon-button" onClick={togglePlayback} disabled={!videoReady}>{playing ? <Pause size={17}/> : <Play size={17}/>}</button>
                <span>{formatTime(currentTime)}</span>
                <input type="range" min="0" max={Math.max(0, duration)} step="0.1" value={Math.min(currentTime, duration || 0)} onChange={(event) => {
                  const value = Number(event.target.value);
                  if (videoRef.current) videoRef.current.currentTime = value;
                  setCurrentTime(value);
                }} disabled={!videoReady}/>
                <span>{formatTime(duration)}</span>
              </div>
            </>
          ) : (
            <div className="event-video-placeholder"><Film size={30}/><strong>{tr('ویدئوی خروجی در دسترس نیست', 'Processed video is not available')}</strong><span>{tr('ابتدا تحلیل خودکار و ساخت ویدئوی خروجی را کامل کن.', 'Complete automatic analysis and video rendering first.')}</span></div>
          )}
          <div className="event-drawing-toolbar">
            <button type="button" className={drawingMode ? 'active' : ''} onClick={() => setDrawingMode((value) => !value)} disabled={!videoReady}>
              <Crosshair size={16}/>{drawingMode ? tr('پایان رسم', 'Finish drawing') : tr('فعال‌کردن رسم روی تصویر', 'Draw on video')}
            </button>
            <button type="button" onClick={() => setDraftPoints((current) => current.slice(0, -1))} disabled={!draftPoints.length}><Undo2 size={15}/>{tr('حذف نقطه آخر', 'Undo point')}</button>
            <button type="button" onClick={() => setDraftPoints([])} disabled={!draftPoints.length}><Trash2 size={15}/>{tr('پاک‌کردن رسم', 'Clear drawing')}</button>
          </div>
          {drawingMode && <div className="event-draw-hint">{ruleType === 'line_crossing' ? tr('برای تعیین خط مجازی دو نقطه روی تصویر انتخاب کن.', 'Click two points to define the virtual line.') : tr('برای رسم محدوده، حداقل سه نقطه روی تصویر انتخاب کن.', 'Click at least three points to draw a zone.')}</div>}
          {!workspace?.tracking_ready && <div className="event-inline-warning"><AlertTriangle size={16}/>{tr('برای این ویدئو هنوز Tracking تکمیل‌شده‌ای وجود ندارد.', 'This video does not have a completed tracking run yet.')}</div>}
          {workspace?.tracking_ready && <div className="event-inline-ready"><CheckCircle2 size={16}/>{tr(`رهگیری آماده است · اجرای شماره ${workspace.tracking_run_id}`, `Tracking is ready · Run #${workspace.tracking_run_id}`)}</div>}
        </div>

        <div className="panel event-panel event-rule-panel">
          <div className="event-panel-heading">
            <div><span className="eyebrow">{tr('قوانین تحلیل', 'ANALYTICS RULES')}</span><h2>{tr('ساخت قانون امنیتی', 'Create Security Rule')}</h2></div>
            <ShieldAlert size={20}/>
          </div>
          <div className="event-form-grid">
            <label className="event-field event-field-wide">
              {tr('نام قانون', 'Rule name')}
              <input value={ruleName} onChange={(event) => setRuleName(event.target.value)} placeholder={tr('مثلاً ورود به محوطه ممنوعه', 'e.g. Restricted area entry')}/>
            </label>
            <label className="event-field event-field-wide">
              {tr('دامنه اعمال قانون', 'Rule scope')}
              <select value={ruleScope} onChange={(event) => setRuleScope(event.target.value as 'asset' | 'camera')}>
                <option value="asset">{tr('فقط همین ویدئو', 'This video only')}</option>
                <option value="camera" disabled={!selectedVideo?.camera_id}>{tr('تمام ویدئوهای این دوربین', 'All videos from this camera')}</option>
              </select>
            </label>
            <label className="event-field event-field-wide">
              {tr('نوع قانون', 'Rule type')}
              <select value={ruleType} onChange={(event) => { setRuleType(event.target.value as RuleType); setDraftPoints([]); }}>
                <option value="zone_intrusion">{tr('ورود به محدوده (Polygon)', 'Zone intrusion (Polygon)')}</option>
                <option value="line_crossing">{tr('عبور از خط مجازی', 'Virtual line crossing')}</option>
                <option value="loitering">{tr('توقف طولانی در محدوده', 'Loitering in zone')}</option>
              </select>
            </label>
            <label className="event-field event-field-wide">
              {tr('کلاس اشیا (با کاما جدا کن)', 'Object classes (comma separated)')}
              <input value={labelsText} onChange={(event) => setLabelsText(event.target.value)} placeholder="person, car, bicycle"/>
            </label>
            <label className="event-field">
              {tr('حداقل اطمینان', 'Minimum confidence')}
              <input type="number" min="0" max="1" step="0.05" value={minimumConfidence} onChange={(event) => setMinimumConfidence(event.target.value)}/>
            </label>
            <label className="event-field">
              {tr('نقطه مرجع شیء', 'Object anchor')}
              <select value={anchor} onChange={(event) => setAnchor(event.target.value as typeof anchor)}>
                <option value="bottom_center">{tr('مرکز پایین کادر', 'Bottom center')}</option>
                <option value="center">{tr('مرکز کادر', 'Bounding-box center')}</option>
              </select>
            </label>
            {ruleType === 'line_crossing' && <label className="event-field event-field-wide">
              {tr('جهت مجاز عبور', 'Allowed crossing direction')}
              <select value={direction} onChange={(event) => setDirection(event.target.value as typeof direction)}>
                <option value="both">{tr('هر دو جهت', 'Both directions')}</option>
                <option value="negative_to_positive">{tr('منفی به مثبت', 'Negative to positive')}</option>
                <option value="positive_to_negative">{tr('مثبت به منفی', 'Positive to negative')}</option>
              </select>
            </label>}
            {ruleType === 'loitering' && <label className="event-field event-field-wide">
              {tr('مدت توقف (ثانیه)', 'Dwell time (seconds)')}
              <input type="number" min="0.1" max="86400" step="0.5" value={dwellSeconds} onChange={(event) => setDwellSeconds(event.target.value)}/>
            </label>}
          </div>
          <div className="event-rule-submit-row">
            <span>{tr(`نقاط رسم‌شده: ${draftPoints.length}`, `Drawn points: ${draftPoints.length}`)}</span>
            <button type="button" onClick={() => void saveRule()} disabled={savingRule || !selectedAssetId || !videoReady || draftPoints.length < (ruleType === 'line_crossing' ? 2 : 3)}>
              {savingRule ? <Loader2 className="spin" size={16}/> : <Plus size={16}/>}{tr('ذخیره قانون', 'Save rule')}
            </button>
          </div>

          <div className="event-saved-rules-heading"><strong>{tr('قوانین ذخیره‌شده برای این ویدئو', 'Saved rules for this video')}</strong><span>{rules.length}</span></div>
          {loading && !rules.length ? <div className="event-empty-small"><Loader2 className="spin" size={16}/>{tr('در حال بارگذاری…', 'Loading…')}</div> : rules.length === 0 ? <div className="event-empty-small">{tr('هنوز قانونی برای این ویدئو تعریف نشده است.', 'No rules have been defined for this video yet.')}</div> : (
            <div className="event-rule-list">
              {rules.map((rule, index) => <div className="event-rule-row" key={rule.id}>
                <span className="event-rule-color" style={{ background: eventColors[index % eventColors.length] }}/>
                <div><strong>{rule.name}</strong><small>{ruleTypeLabel(rule.rule_type)} · {rule.labels.length ? rule.labels.join(', ') : tr('همه اشیا', 'All objects')} · {rule.scope === 'camera' ? tr('دامنه دوربین', 'Camera-wide') : tr('همین ویدئو', 'This video')}</small></div>
                <button type="button" onClick={() => void deleteRule(rule.id)} aria-label={tr('حذف قانون', 'Delete rule')}><Trash2 size={15}/></button>
              </div>)}
            </div>
          )}
          <button type="button" className="event-analyze-button" onClick={() => void analyzeEvents()} disabled={analyzing || !workspace?.tracking_ready || rules.filter((rule) => rule.is_active).length === 0}>
            {analyzing ? <Loader2 className="spin" size={17}/> : <Activity size={17}/>}{tr('اجرای قوانین روی Tracking فعلی', 'Evaluate rules on latest tracking')}
          </button>
          <div className="event-rule-footnote">{tr('اگر قانون قبل از تحلیل ویدئوی جدید ساخته شود، پس از SORT به‌صورت خودکار اجرا خواهد شد. برای ویدئوهای تحلیل‌شده قبلی از دکمه بالا استفاده کن.', 'Rules created before a new video analysis run will execute automatically after SORT. Use the button above for videos already processed.')}</div>
        </div>
      </section>

      <section className="panel event-results-panel">
        <div className="event-results-header">
          <div><span className="eyebrow">{tr('مرکز رخدادها', 'INCIDENT CENTER')}</span><h2>{tr('رویدادهای شناسایی‌شده', 'Detected Security Events')}</h2><p>{tr('رویدادها از مسیر حرکت Trackها استخراج شده‌اند؛ هر مورد به زمان وقوع در ویدئو متصل است.', 'Events are derived from track movement. Each incident links to its exact video timestamp.')}</p></div>
          <button type="button" className="event-refresh-button" onClick={() => selectedAssetId && void loadRulesAndEvents(selectedAssetId)}><RefreshCw size={15}/>{tr('بازخوانی', 'Refresh')}</button>
        </div>
        <div className="event-stats-grid">
          <div><BellRing size={17}/><span>{tr('کل رویدادها', 'Total events')}</span><strong>{events.length}</strong></div>
          <div><AlertTriangle size={17}/><span>{tr('جدید', 'New')}</span><strong>{statusCounts.new}</strong></div>
          <div><Check size={17}/><span>{tr('تأییدشده', 'Acknowledged')}</span><strong>{statusCounts.acknowledged}</strong></div>
          <div><CheckCircle2 size={17}/><span>{tr('رسیدگی‌شده', 'Resolved')}</span><strong>{statusCounts.resolved}</strong></div>
        </div>
        <div className="event-filters">
          {(['all', 'new', 'acknowledged', 'investigating', 'resolved', 'false_positive'] as const).map((value) => <button type="button" key={value} className={eventFilter === value ? 'active' : ''} onClick={() => setEventFilter(value)}>{value === 'all' ? tr('همه', 'All') : eventStatusLabel(value)}</button>)}
        </div>
        {loading && !events.length ? <div className="event-list-empty"><Loader2 className="spin" size={20}/>{tr('در حال دریافت رویدادها…', 'Loading events…')}</div> : visibleEvents.length === 0 ? <div className="event-list-empty"><BellRing size={27}/><strong>{tr('رویدادی برای نمایش وجود ندارد', 'No events to display')}</strong><span>{tr('قانون تعریف کن و آن را روی اجرای رهگیری‌شده اعمال کن.', 'Create a rule and evaluate it against a completed tracking run.')}</span></div> : (
          <div className="event-table-wrap">
            <table className="event-table">
              <thead><tr>
                <th>{tr('رویداد', 'Event')}</th><th>{tr('شیء / Track', 'Object / Track')}</th><th>{tr('زمان ویدئو', 'Video time')}</th><th>{tr('اطمینان', 'Confidence')}</th><th>{tr('وضعیت', 'Status')}</th><th>{tr('اقدام', 'Action')}</th>
              </tr></thead>
              <tbody>
                {visibleEvents.map((item) => <tr key={item.id} className={selectedEventId === item.id ? 'selected' : ''}>
                  <td><strong>{ruleTypeLabel(item.event_type)}</strong><small>{item.rule_name}</small></td>
                  <td><strong>{item.label}</strong><small>Track #{item.track_number} · Frame {item.frame_number}</small></td>
                  <td><button type="button" className="event-time-link" onClick={() => seekToEvent(item)}><Clock3 size={14}/>{formatTime(item.timestamp_seconds)}</button></td>
                  <td>{Math.round(item.confidence * 100)}%</td>
                  <td><span className={`event-status status-${item.status}`}>{eventStatusLabel(item.status)}</span></td>
                  <td className="event-row-actions">
                    <button type="button" title={tr('رفتن به لحظه وقوع', 'Jump to evidence')} onClick={() => seekToEvent(item)}><Play size={14}/></button>
                    {item.status === 'new' && <button type="button" title={tr('تأیید رویداد', 'Acknowledge')} onClick={() => void updateEventStatus(item, 'acknowledged')}><Check size={14}/></button>}
                    {(item.status === 'new' || item.status === 'acknowledged') && <button type="button" title={tr('بستن رویداد', 'Resolve')} onClick={() => void updateEventStatus(item, 'resolved')}><CheckCircle2 size={14}/></button>}
                    {item.status !== 'false_positive' && item.status !== 'resolved' && <button type="button" title={tr('ثبت خطای تشخیص', 'Mark false positive')} onClick={() => void updateEventStatus(item, 'false_positive')}><Minus size={14}/></button>}
                  </td>
                </tr>)}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
