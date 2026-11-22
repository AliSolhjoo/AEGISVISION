import { t, useLanguage } from '../i18n';
import { useEffect, useState } from 'react';
import { Camera, CircleDot, RadioTower, ShieldAlert, VideoOff, Wifi } from 'lucide-react';
import type { Camera as CameraType } from '../lib/types';
import { api, describeApiError } from '../lib/api';
import { formatDate, titleCase } from '../lib/format';
import { useOrganizations } from '../context/OrganizationContext';
import { LoadingState, PageHeader, EmptyState, Button } from '../components/Ui';
import StatusBadge from '../components/StatusBadge';

export default function MonitoringPage() {
  
  useLanguage();
const { activeOrganization } = useOrganizations();
  const [cameras, setCameras] = useState<CameraType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const refresh = async () => {
    if (!activeOrganization) { setCameras([]); setLoading(false); return; }
    setLoading(true); setError('');
    try { setCameras(await api.get<CameraType[]>(`/api/organizations/${activeOrganization.id}/cameras/`)); }
    catch (err) { setError(describeApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, [activeOrganization?.id]);
  return <>
    <PageHeader eyebrow={t("OPERATIONS / CAMERA WALL")} title={t("Live monitoring")} description={t("Operational source overview and camera readiness for the active workspace.")} actions={<Button variant="secondary" onClick={() => void refresh()}>{t("Refresh status")}</Button>}/>
    <div className="monitoring-banner"><div className="monitoring-banner-icon"><RadioTower size={22}/></div><div><strong>{t("Live stream transport is not connected yet")}</strong><p>{t("The current backend registers camera metadata but does not open RTSP streams or maintain live health checks. This view shows actual API-reported status only.")}</p></div><span className="status-badge status-pending"><i/>{t("STREAM WORKER PLANNED")}</span></div>
    {loading ? <LoadingState/> : error ? <div className="notice notice-error">{t(error)}</div> : cameras.length === 0 ? <EmptyState title={t("No camera sources")} description={t("Register camera sources to populate this monitoring workspace.")}/> : <div className="monitor-camera-grid">{cameras.map((camera) => <article className="monitor-camera-card" key={camera.id}><div className="monitor-feed"><div className="monitor-feed-noise"/><div className="feed-camera-icon"><Camera size={30}/></div><div className="feed-label">{t("SOURCE ")}{String(camera.id).padStart(3, '0')}</div><div className="feed-status"><StatusBadge status={camera.is_enabled ? camera.status : 'disabled'}/></div><div className="feed-unavailable"><VideoOff size={19}/><span>{t("No live frames available")}</span></div></div><div className="monitor-camera-info"><div><h3>{camera.name}</h3><p>{camera.location || camera.code}</p></div><div className="monitor-camera-meta"><span><CircleDot size={13}/>{t(titleCase(camera.source_type))}</span><span><Wifi size={13}/>{camera.last_seen_at ? formatDate(camera.last_seen_at) : t('No heartbeat received')}</span></div></div></article>)}</div>}
    <div className="notice notice-info"><ShieldAlert size={17}/><span>{t("Do not use the API-reported status as proof of real-time connectivity in this release. A future stream worker will probe RTSP sources and publish heartbeat updates before this page can show live availability.")}</span></div>
  </>;
}
