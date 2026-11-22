import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Activity, AlertOctagon, AlertTriangle, ArrowUpRight,
  BellRing, Camera, CheckCircle2, ChevronRight, Clock3, Download,
  Filter, ListFilter, Loader2, MessageSquare, RefreshCw, Search,
  ShieldAlert, ShieldCheck, Siren, UserRound, Users, X,
} from 'lucide-react';
import { PageHeader } from '../components/Ui';
import { useOrganizations } from '../context/OrganizationContext';
import { api, describeApiError } from '../lib/api';
import { useLanguage, t } from '../i18n';

type Severity = 'critical' | 'high' | 'medium' | 'low';
type EventStatus = 'new' | 'acknowledged' | 'investigating' | 'resolved' | 'false_positive';
type SocUser = { id: number; email: string; full_name: string; role?: string };
type SocEvent = {
  id: number; organization_id: string; asset_id: number; asset_name: string;
  tracking_run_id: number; rule_id: number | null; rule_name: string;
  event_type: string; track_number: number; label: string;
  timestamp_seconds: number; frame_number: number; confidence: number;
  details: Record<string, unknown>; status: EventStatus; severity: Severity;
  assigned_to_id: number | null; assigned_to: SocUser | null;
  camera_id: number | null; camera_name: string | null;
  acknowledged_at: string | null; resolved_at: string | null;
  created_at: string; updated_at: string;
};
type ActivityItem = {
  id: number; action: 'created' | 'status_changed' | 'assigned' | 'severity_changed' | 'comment';
  actor: SocUser | null; from_status: string; to_status: string;
  from_severity: string; to_severity: string;
  from_assignee: { id: number; full_name: string } | null;
  to_assignee: { id: number; full_name: string } | null;
  note: string; created_at: string;
};
type Dashboard = {
  generated_at: string;
  permissions?: { can_manage_events: boolean; can_export: boolean };
  summary: {
    total_events: number; open_events: number; critical_open: number; high_open: number;
    new_today: number; resolved_today: number; unassigned_open: number; investigating: number;
  };
  by_severity: Record<Severity, number>;
  by_status: Record<EventStatus, number>;
  trend_7d: { date: string; count: number }[];
  top_cameras: { camera_id: number; camera_name: string; events: number }[];
  recent_events: SocEvent[];
};
type EventListResponse = { count: number; offset: number; limit: number; results: SocEvent[] };

const statusKeys: Record<EventStatus, string> = {
  new: 'New', acknowledged: 'Acknowledged', investigating: 'Investigating',
  resolved: 'Resolved', false_positive: 'False positive',
};
const severityKeys: Record<Severity, string> = {
  critical: 'Critical', high: 'High', medium: 'Medium', low: 'Low',
};
const eventTypeKeys: Record<string, string> = {
  zone_intrusion: 'Zone intrusion', line_crossing: 'Line crossing', loitering: 'Loitering',
};
const activityKeys: Record<ActivityItem['action'], string> = {
  created: 'Event created', status_changed: 'Status updated', assigned: 'Assignment changed',
  severity_changed: 'Severity changed', comment: 'Investigation note',
};

function displayDate(value: string, language: string, withTime = false) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return date.toLocaleString(language === 'fa' ? 'fa-IR' : 'en-US', withTime
    ? { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }
    : { month: 'short', day: 'numeric' });
}
function formatNumber(value: number, language: string) {
  return Number(value).toLocaleString(language === 'fa' ? 'fa-IR' : 'en-US');
}
function displayClock(seconds: number, language: string) {
  const value = Math.max(0, Number(seconds) || 0);
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const rest = Math.floor(value % 60);
  const clock = hours ? `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}` : `${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`;
  return language === 'fa' ? clock.replace(/[0-9]/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)]) : clock;
}
function statusLabel(value: EventStatus) { return t(statusKeys[value] || value); }
function severityLabel(value: Severity) { return t(severityKeys[value] || value); }
function eventTypeLabel(value: string) { return t(eventTypeKeys[value] || value.replaceAll('_', ' ')); }

export default function SOCPage() {
  const { activeOrganization } = useOrganizations();
  const { language } = useLanguage();
  const navigate = useNavigate();
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [events, setEvents] = useState<SocEvent[]>([]);
  const [eventCount, setEventCount] = useState(0);
  const [assignees, setAssignees] = useState<SocUser[]>([]);
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const [activities, setActivities] = useState<ActivityItem[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | EventStatus>('all');
  const [severityFilter, setSeverityFilter] = useState<'all' | Severity>('all');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [actionBusy, setActionBusy] = useState(false);
  const [note, setNote] = useState('');
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const hasAutoSelectedEvent = useRef(false);

  const base = activeOrganization ? `/api/organizations/${activeOrganization.id}` : '';
  const selectedEvent = useMemo(
    () => events.find((item) => item.id === selectedEventId) || dashboard?.recent_events.find((item) => item.id === selectedEventId) || null,
    [events, dashboard, selectedEventId],
  );

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    params.set('limit', '150');
    if (search.trim()) params.set('q', search.trim());
    if (statusFilter !== 'all') params.set('status', statusFilter);
    if (severityFilter !== 'all') params.set('severity', severityFilter);
    return params.toString();
  }, [search, statusFilter, severityFilter]);

  const refreshAll = useCallback(async (silent = false) => {
    if (!activeOrganization) {
      setDashboard(null); setEvents([]); setEventCount(0); setLoading(false); return;
    }
    if (silent) setRefreshing(true); else setLoading(true);
    try {
      const [dash, list] = await Promise.all([
        api.get<Dashboard>(`${base}/soc/dashboard/`),
        api.get<EventListResponse>(`${base}/soc/events/?${queryString}`),
      ]);
      setDashboard(dash);
      setEvents(list.results);
      setEventCount(list.count);
      setLastUpdated(dash.generated_at);
      setError('');
      setSelectedEventId((current) => {
        if (current && list.results.some((item) => item.id === current)) return current;
        if (current && !list.results.some((item) => item.id === current)) return list.results[0]?.id ?? null;
        if (!hasAutoSelectedEvent.current) {
          hasAutoSelectedEvent.current = true;
          return list.results[0]?.id ?? null;
        }
        return null;
      });
    } catch (reason) {
      setError(describeApiError(reason));
    } finally {
      setLoading(false); setRefreshing(false);
    }
  }, [activeOrganization?.id, base, queryString]);

  useEffect(() => {
    void refreshAll(false);
    if (!activeOrganization) return;
    let timer: number | undefined;
    const start = () => { timer = window.setInterval(() => { if (!document.hidden) void refreshAll(true); }, 15000); };
    start();
    return () => { if (timer) window.clearInterval(timer); };
  }, [refreshAll, activeOrganization?.id]);

  useEffect(() => {
    if (!activeOrganization) { setAssignees([]); return; }
    let cancelled = false;
    api.get<SocUser[]>(`${base}/soc/assignees/`).then((rows) => { if (!cancelled) setAssignees(rows); }).catch(() => { if (!cancelled) setAssignees([]); });
    return () => { cancelled = true; };
  }, [activeOrganization?.id, base]);

  useEffect(() => {
    if (!selectedEventId || !activeOrganization) { setActivities([]); return; }
    let cancelled = false;
    api.get<ActivityItem[]>(`${base}/events/${selectedEventId}/activity/`)
      .then((items) => { if (!cancelled) setActivities(items); })
      .catch(() => { if (!cancelled) setActivities([]); });
    return () => { cancelled = true; };
  }, [selectedEventId, activeOrganization?.id, base]);

  async function updateEvent(id: number, patch: Record<string, unknown>) {
    if (!activeOrganization) return;
    setActionBusy(true); setError('');
    try {
      await api.patch<SocEvent>(`${base}/events/${id}/`, patch);
      if (patch.note) setNote('');
      await refreshAll(true);
      const rows = await api.get<ActivityItem[]>(`${base}/events/${id}/activity/`);
      setActivities(rows);
    } catch (reason) {
      setError(describeApiError(reason));
    } finally {
      setActionBusy(false);
    }
  }

  async function exportCsv() {
    if (!activeOrganization) return;
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set('q', search.trim());
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (severityFilter !== 'all') params.set('severity', severityFilter);
      const blob = await api.blob(`${base}/soc/events/export.csv?${params.toString()}`);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `aegisvision-soc-${new Date().toISOString().slice(0, 10)}.csv`;
      document.body.appendChild(anchor); anchor.click(); anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1500);
    } catch (reason) { setError(describeApiError(reason)); }
  }

  const summary = dashboard?.summary;
  const trendMax = Math.max(1, ...(dashboard?.trend_7d.map((item) => item.count) || [0]));
  const criticalTotal = dashboard?.by_severity.critical ?? 0;
  const highTotal = dashboard?.by_severity.high ?? 0;
  const canManageEvents = dashboard?.permissions?.can_manage_events ?? false;
  const selectedActionsDisabled = actionBusy || !selectedEvent || !canManageEvents;

  return <div className="soc-page" dir={language === 'fa' ? 'rtl' : 'ltr'}>
    <PageHeader
      eyebrow={t('SECURITY OPERATIONS / SOC')}
      title={t('Security Operations Center')}
      description={t('Monitor incidents, coordinate response, and maintain an auditable security workflow.')}
      actions={<>
        <span className="soc-live-indicator"><i/> {t('Live updates every 15 seconds')}</span>
        <button className="soc-header-button" onClick={() => void refreshAll(true)} disabled={refreshing}><RefreshCw size={15} className={refreshing ? 'spin' : ''}/>{t('Refresh')}</button>
        <button className="soc-header-button soc-export-button" onClick={() => void exportCsv()}><Download size={15}/>{t('Export CSV')}</button>
      </>}
    />

    {error && <div className="soc-error"><AlertTriangle size={16}/><span>{error}</span><button onClick={() => setError('')} aria-label={t('Dismiss')}><X size={15}/></button></div>}

    <div className="soc-overview-strip">
      <div><span>{t('Operations status')}</span><strong><i className="soc-status-dot"/>{t('Monitoring active')}</strong></div>
      <div><span>{t('Workspace')}</span><strong>{activeOrganization?.name || t('No workspace')}</strong></div>
      <div><span>{t('Last synchronized')}</span><strong>{lastUpdated ? displayDate(lastUpdated, language, true) : '—'}</strong></div>
      <div><span>{t('Assigned operations team')}</span><strong><Users size={14}/>{formatNumber(assignees.length, language)}</strong></div>
    </div>

    <section className="soc-kpi-grid">
      <article className="soc-kpi-card soc-kpi-open"><div className="soc-kpi-icon"><ShieldAlert size={19}/></div><span>{t('Open incidents')}</span><strong>{summary ? formatNumber(summary.open_events, language) : '—'}</strong><small>{t('Awaiting closure')}</small></article>
      <article className="soc-kpi-card soc-kpi-critical"><div className="soc-kpi-icon"><Siren size={19}/></div><span>{t('Critical open')}</span><strong>{summary ? formatNumber(summary.critical_open, language) : '—'}</strong><small>{t('Immediate attention')}</small></article>
      <article className="soc-kpi-card soc-kpi-investigating"><div className="soc-kpi-icon"><Activity size={19}/></div><span>{t('Under investigation')}</span><strong>{summary ? formatNumber(summary.investigating, language) : '—'}</strong><small>{t('Active response')}</small></article>
      <article className="soc-kpi-card soc-kpi-unassigned"><div className="soc-kpi-icon"><UserRound size={19}/></div><span>{t('Unassigned open')}</span><strong>{summary ? formatNumber(summary.unassigned_open, language) : '—'}</strong><small>{t('Needs an owner')}</small></article>
      <article className="soc-kpi-card soc-kpi-new"><div className="soc-kpi-icon"><BellRing size={19}/></div><span>{t('New today')}</span><strong>{summary ? formatNumber(summary.new_today, language) : '—'}</strong><small>{t('Created today')}</small></article>
      <article className="soc-kpi-card soc-kpi-resolved"><div className="soc-kpi-icon"><CheckCircle2 size={19}/></div><span>{t('Resolved today')}</span><strong>{summary ? formatNumber(summary.resolved_today, language) : '—'}</strong><small>{t('Closed today')}</small></article>
    </section>

    <section className="soc-insights-grid">
      <article className="soc-card soc-trend-card">
        <div className="soc-card-heading"><div><span className="soc-eyebrow">{t('INCIDENT ACTIVITY')}</span><h2>{t('Seven-day event trend')}</h2><p>{t('Security events recorded by day in this workspace.')}</p></div><div className="soc-card-heading-icon"><Activity size={18}/></div></div>
        <div className="soc-trend-chart" role="img" aria-label={t('Seven-day event trend')}>
          {(dashboard?.trend_7d || []).map((item) => <div className="soc-trend-column" key={item.date}>
            <span>{formatNumber(item.count, language)}</span><div className="soc-trend-bar-track"><i style={{ height: `${Math.max(item.count ? 8 : 2, item.count / trendMax * 100)}%` }}/></div>
            <small>{displayDate(item.date, language)}</small>
          </div>)}
          {!dashboard?.trend_7d.length && <div className="soc-empty-chart">{t('No activity data yet')}</div>}
        </div>
      </article>
      <article className="soc-card soc-severity-card">
        <div className="soc-card-heading"><div><span className="soc-eyebrow">{t('RISK DISTRIBUTION')}</span><h2>{t('Events by severity')}</h2><p>{t('All detected events, grouped by priority.')}</p></div><div className="soc-card-heading-icon"><AlertOctagon size={18}/></div></div>
        <div className="soc-severity-list">
          {(['critical', 'high', 'medium', 'low'] as Severity[]).map((severity) => {
            const count = dashboard?.by_severity[severity] ?? 0;
            const total = dashboard ? Math.max(1, dashboard.summary.total_events) : 1;
            return <div className={`soc-severity-row severity-${severity}`} key={severity}>
              <div><span className="soc-severity-dot"/><strong>{severityLabel(severity)}</strong><b>{count}</b></div>
              <div className="soc-severity-track"><i style={{ width: `${Math.min(100, count / total * 100)}%` }}/></div>
            </div>;
          })}
        </div>
        <div className="soc-severity-footer"><span>{t('Critical + High')}</span><strong>{formatNumber(criticalTotal + highTotal, language)}</strong></div>
      </article>
      <article className="soc-card soc-camera-card">
        <div className="soc-card-heading"><div><span className="soc-eyebrow">{t('SOURCE PERFORMANCE')}</span><h2>{t('Top event sources')}</h2><p>{t('Cameras with the highest event volume.')}</p></div><div className="soc-card-heading-icon"><Camera size={18}/></div></div>
        <div className="soc-camera-list">
          {(dashboard?.top_cameras || []).map((item, index) => <div className="soc-camera-row" key={item.camera_id}>
            <span className="soc-camera-rank">{formatNumber(index + 1, language)}</span><div><strong>{item.camera_name}</strong><small>{t('Security events')}</small></div><b>{formatNumber(item.events, language)}</b>
          </div>)}
          {!dashboard?.top_cameras.length && <div className="soc-empty-inline"><Camera size={18}/>{t('No camera-linked events yet')}</div>}
        </div>
      </article>
    </section>

    <section className="soc-events-section soc-card">
      <div className="soc-card-heading soc-events-heading"><div><span className="soc-eyebrow">{t('INCIDENT RESPONSE')}</span><h2>{t('Incident queue')}</h2><p>{t('Review, assign, investigate, and close security events.')}</p></div><div className="soc-queue-meta"><span>{eventCount.toLocaleString(language === 'fa' ? 'fa-IR' : 'en-US')} {t('events')}</span><span className="soc-auto-refresh"><i/>{t('Auto-refresh')}</span></div></div>
      <div className="soc-toolbar">
        <label className="soc-search"><Search size={15}/><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder={t('Search incidents, cameras, assets…')}/></label>
        <label className="soc-select-filter"><Filter size={14}/><select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value as 'all' | EventStatus)}>
          <option value="all">{t('All statuses')}</option>
          {(['new', 'acknowledged', 'investigating', 'resolved', 'false_positive'] as EventStatus[]).map((item) => <option value={item} key={item}>{statusLabel(item)}</option>)}
        </select></label>
        <label className="soc-select-filter"><ListFilter size={14}/><select value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value as 'all' | Severity)}>
          <option value="all">{t('All severities')}</option>
          {(['critical', 'high', 'medium', 'low'] as Severity[]).map((item) => <option value={item} key={item}>{severityLabel(item)}</option>)}
        </select></label>
      </div>

      {loading ? <div className="soc-loading"><Loader2 className="spin" size={20}/>{t('Loading security operations data…')}</div> : events.length === 0 ? <div className="soc-empty"><ShieldCheck size={28}/><strong>{t('No incidents match these filters')}</strong><span>{t('New security events will appear here when analytics rules are triggered.')}</span></div> : <div className="soc-table-wrap">
        <table className="soc-table"><thead><tr>
          <th>{t('Incident')}</th><th>{t('Source')}</th><th>{t('Severity')}</th><th>{t('Status')}</th><th>{t('Assignee')}</th><th>{t('Detected')}</th><th>{t('Confidence')}</th>
        </tr></thead><tbody>
          {events.map((item) => <tr key={item.id} className={selectedEventId === item.id ? 'is-selected' : ''} onClick={() => setSelectedEventId(item.id)}>
            <td><div className="soc-incident-cell"><span className={`soc-event-type-icon event-${item.event_type}`}><AlertTriangle size={15}/></span><div><strong>{item.rule_name}</strong><small>{eventTypeLabel(item.event_type)} · #{item.id}</small></div></div></td>
            <td><strong>{item.camera_name || item.asset_name}</strong><small>{item.label} · Track #{formatNumber(item.track_number, language)}</small></td>
            <td><span className={`soc-severity-badge severity-${item.severity}`}>{severityLabel(item.severity)}</span></td>
            <td><span className={`soc-status-badge status-${item.status}`}>{statusLabel(item.status)}</span></td>
            <td><span className="soc-assignee-cell"><UserRound size={13}/>{item.assigned_to?.full_name || t('Unassigned')}</span></td>
            <td><strong>{displayDate(item.created_at, language)}</strong><small>{displayClock(item.timestamp_seconds, language)} {t('video time')}</small></td>
            <td><span className="soc-confidence">{formatNumber(Math.round(item.confidence * 100), language)}%</span></td>
          </tr>)}
        </tbody></table>
      </div>}
    </section>

    {selectedEvent && <aside className="soc-detail-panel" aria-label={t('Incident detail')}>
      <div className="soc-detail-header"><div><span className="soc-eyebrow">{t('CASE FILE')} / #{selectedEvent.id}</span><h2>{selectedEvent.rule_name}</h2><p>{selectedEvent.asset_name}</p></div><button className="soc-close-detail" onClick={() => setSelectedEventId(null)} aria-label={t('Close')}><X size={17}/></button></div>
      <div className="soc-detail-tags"><span className={`soc-severity-badge severity-${selectedEvent.severity}`}>{severityLabel(selectedEvent.severity)}</span><span className={`soc-status-badge status-${selectedEvent.status}`}>{statusLabel(selectedEvent.status)}</span></div>
      <div className="soc-detail-metrics">
        <div><small>{t('Object')}</small><strong>{selectedEvent.label}</strong></div>
        <div><small>{t('Track ID')}</small><strong>#{formatNumber(selectedEvent.track_number, language)}</strong></div>
        <div><small>{t('Video timestamp')}</small><strong>{displayClock(selectedEvent.timestamp_seconds, language)}</strong></div>
        <div><small>{t('Confidence')}</small><strong>{formatNumber(Math.round(selectedEvent.confidence * 100), language)}%</strong></div>
      </div>
      <div className="soc-detail-actions">
        <button onClick={() => navigate(`/events?video_id=${selectedEvent.asset_id}`)}><ArrowUpRight size={14}/>{t('Open event evidence')}</button>
      </div>
      {!canManageEvents && <div className="soc-readonly-note">{t('Your role has read-only access to incident records.')}</div>}
      <div className="soc-detail-field"><label>{t('Incident status')}</label><select disabled={selectedActionsDisabled} value={selectedEvent.status} onChange={(event) => void updateEvent(selectedEvent.id, { status: event.target.value })}>
        {(['new', 'acknowledged', 'investigating', 'resolved', 'false_positive'] as EventStatus[]).map((item) => <option value={item} key={item}>{statusLabel(item)}</option>)}
      </select></div>
      <div className="soc-detail-field"><label>{t('Severity')}</label><select disabled={selectedActionsDisabled} value={selectedEvent.severity} onChange={(event) => void updateEvent(selectedEvent.id, { severity: event.target.value })}>
        {(['critical', 'high', 'medium', 'low'] as Severity[]).map((item) => <option value={item} key={item}>{severityLabel(item)}</option>)}
      </select></div>
      <div className="soc-detail-field"><label>{t('Assign to')}</label><select disabled={selectedActionsDisabled} value={selectedEvent.assigned_to_id ?? ''} onChange={(event) => void updateEvent(selectedEvent.id, { assigned_to_id: event.target.value || null })}>
        <option value="">{t('Unassigned')}</option>
        {assignees.map((person) => <option value={person.id} key={person.id}>{person.full_name} · {t(person.role || 'operator')}</option>)}
      </select></div>
      <div className="soc-detail-field"><label>{t('Investigation note')}</label><textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={2000} rows={3} placeholder={t('Add an operational note…')}/><button className="soc-note-submit" disabled={!note.trim() || actionBusy} onClick={() => void updateEvent(selectedEvent.id, { note })}><MessageSquare size={14}/>{t('Add note')}</button></div>
      <div className="soc-activity-heading"><div><span className="soc-eyebrow">{t('AUDIT TRAIL')}</span><h3>{t('Incident activity')}</h3></div><span>{formatNumber(activities.length, language)}</span></div>
      <div className="soc-activity-list">
        {activities.map((item) => <div className="soc-activity-item" key={item.id}><span className={`soc-activity-dot action-${item.action}`}/><div><strong>{t(activityKeys[item.action])}</strong><small>{item.actor?.full_name || t('System')} · {displayDate(item.created_at, language, true)}</small>
          {item.from_status && item.to_status && <p>{statusLabel(item.from_status as EventStatus)} <ChevronRight size={12}/> {statusLabel(item.to_status as EventStatus)}</p>}
          {item.from_severity && item.to_severity && <p>{severityLabel(item.from_severity as Severity)} <ChevronRight size={12}/> {severityLabel(item.to_severity as Severity)}</p>}
          {item.to_assignee && <p>{t('Assigned to')} {item.to_assignee.full_name}</p>}
          {item.note && <blockquote>{t(item.note)}</blockquote>}
        </div></div>)}
        {!activities.length && <div className="soc-empty-activity">{t('No activity recorded yet')}</div>}
      </div>
    </aside>}

    <div className="soc-bottom-note"><ShieldCheck size={14}/><span>{t('All incident actions are recorded in the organization audit trail.')}</span><span><Clock3 size={13}/>{t('Polling interval: 15 seconds')}</span></div>
  </div>;
}
