import { t, useLanguage } from '../i18n';
import type { ReactNode } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Activity, ArrowUpRight, Camera, Clock3, Cpu, Film, Layers3, Radar, ShieldCheck } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, PieChart, Pie, Cell } from 'recharts';
import { api, describeApiError } from '../lib/api';
import type { Camera as CameraType, VideoAsset } from '../lib/types';
import { formatBytes, formatDate, formatRelative } from '../lib/format';
import { useOrganizations } from '../context/OrganizationContext';
import { PageHeader, LoadingState, SectionHeading, EmptyState, Button } from '../components/Ui';
import StatusBadge from '../components/StatusBadge';

function lastSevenDays(videos: VideoAsset[], language: 'en' | 'fa') {
  const data = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(); date.setDate(date.getDate() - (6 - index));
    return { key: date.toDateString(), label: date.toLocaleDateString(language === 'fa' ? 'fa-IR-u-ca-persian' : 'en-US', { weekday: 'short' }), uploads: 0 };
  });
  videos.forEach((video) => {
    const key = new Date(video.created_at).toDateString();
    const bucket = data.find((item) => item.key === key);
    if (bucket) bucket.uploads += 1;
  });
  return data;
}

export default function OverviewPage() {
  
  const { language } = useLanguage();
  const { activeOrganization } = useOrganizations();
  const [cameras, setCameras] = useState<CameraType[]>([]);
  const [videos, setVideos] = useState<VideoAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const refresh = async () => {
    if (!activeOrganization) { setCameras([]); setVideos([]); setLoading(false); return; }
    setLoading(true); setError('');
    try {
      const [cameraData, videoData] = await Promise.all([
        api.get<CameraType[]>(`/api/organizations/${activeOrganization.id}/cameras/`),
        api.get<VideoAsset[]>(`/api/organizations/${activeOrganization.id}/videos/`),
      ]);
      setCameras(cameraData); setVideos(videoData);
    } catch (err) { setError(describeApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, [activeOrganization?.id]);

  const online = cameras.filter((camera) => camera.status === 'online' && camera.is_enabled).length;
  const offline = cameras.filter((camera) => ['offline', 'error'].includes(camera.status) && camera.is_enabled).length;
  const queued = videos.filter((video) => ['queued', 'processing'].includes(video.status)).length;
  const completed = videos.filter((video) => video.status === 'completed').length;
  const chartData = useMemo(() => lastSevenDays(videos, language), [videos, language]);
  const cameraDistribution = [
    { name: t('Online'), value: online, color: '#35d6a3' },
    { name: t('Offline / Error'), value: offline, color: '#f47786' },
    { name: t('Pending / Disabled'), value: Math.max(0, cameras.length - online - offline), color: '#5b6a88' },
  ];

  return <>
    <PageHeader eyebrow={t("OPERATIONAL INTELLIGENCE / OVERVIEW")} title={t("Good to see you.")} description={t(activeOrganization ? `Here’s the latest operational picture for ${activeOrganization.name}.` : 'Create or select a workspace to begin monitoring your environment.')} actions={<Button variant="secondary" onClick={() => void refresh()}><Activity size={16}/> {t("Refresh data")}</Button>}/>
    {!activeOrganization ? <EmptyState title={t("No workspace selected")} description={t("Create an organization before adding cameras and analyzing video.")} action={<Link className="button button-primary" to="/organizations">{t("Create workspace ")}<ArrowUpRight size={16}/></Link>}/> : loading ? <LoadingState/> : error ? <div className="notice notice-error">{t(error)}</div> : <>
      <div className="metric-grid">
        <MetricCard label={t("Registered cameras")} value={cameras.length} meta={`${online} online now`} icon={<Camera size={19}/>} tone="blue"/>
        <MetricCard label={t("Video assets")} value={videos.length} meta={`${completed} processed`} icon={<Film size={19}/>} tone="violet"/>
        <MetricCard label={t("Processing queue")} value={queued} meta="Awaiting worker execution" icon={<Cpu size={19}/>} tone="amber"/>
        <MetricCard label={t("Extracted frames")} value={videos.reduce((sum, item) => sum + (item.frames_count || 0), 0).toLocaleString(language === 'fa' ? 'fa-IR' : 'en-US')} meta="Across completed assets" icon={<Layers3 size={19}/>} tone="green"/>
      </div>
      <div className="dashboard-grid dashboard-grid-main">
        <section className="panel chart-panel">
          <SectionHeading title={t("Video ingestion")} subtitle={t("Uploads received over the last seven days")} action={<span className="chart-legend"><i/> {t("Video uploads")}</span>}/>
          <div className="chart-wrap"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chartData} margin={{ top: 16, right: 10, left: -18, bottom: 0 }}>
            <defs><linearGradient id="uploadFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5c8dff" stopOpacity={0.28}/><stop offset="100%" stopColor="#5c8dff" stopOpacity={0.01}/></linearGradient></defs>
            <CartesianGrid stroke="#202b41" strokeDasharray="3 5" vertical={false}/><XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#74819b', fontSize: 11 }}/><YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fill: '#74819b', fontSize: 11 }}/><Tooltip contentStyle={{ background: '#121c30', border: '1px solid #2a3852', borderRadius: 12, color: '#f3f6ff' }} labelStyle={{ color: '#9facc4' }}/><Area type="monotone" dataKey="uploads" stroke="#7197ff" strokeWidth={2.5} fill="url(#uploadFill)" activeDot={{ r: 5, strokeWidth: 0 }}/>
          </AreaChart></ResponsiveContainer></div>
          <div className="chart-footnote"><span><Clock3 size={13}/> {t("Updated ")}{formatRelative(new Date().toISOString())}</span><span>{t("Source: organization video assets")}</span></div>
        </section>
        <section className="panel camera-health-panel">
          <SectionHeading title={t("Camera health")} subtitle={t("Current registered source status")}/>
          <div className="donut-area">
            <div className="donut-chart"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={cameraDistribution} dataKey="value" nameKey="name" innerRadius="68%" outerRadius="91%" paddingAngle={3} stroke="none">{cameraDistribution.map((item) => <Cell key={item.name} fill={item.color}/>)}</Pie><Tooltip contentStyle={{ background: '#121c30', border: '1px solid #2a3852', borderRadius: 12, color: '#f3f6ff' }}/></PieChart></ResponsiveContainer><div className="donut-center"><strong>{cameras.length}</strong><span>{t("Sources")}</span></div></div>
          </div>
          <div className="health-legend">{cameraDistribution.map((item) => <div key={item.name}><span className="legend-label"><i style={{ background: item.color }}/>{item.name}</span><strong>{item.value}</strong></div>)}</div>
          <Link className="panel-link" to="/cameras">{t("Manage camera sources ")}<ArrowUpRight size={14}/></Link>
        </section>
      </div>
      <div className="dashboard-grid dashboard-grid-secondary">
        <section className="panel recent-panel">
          <SectionHeading title={t("Recent video assets")} subtitle={t("Latest uploads in this workspace")} action={<Link className="text-link" to="/videos">{t("View library ")}<ArrowUpRight size={14}/></Link>}/>
          {videos.length === 0 ? <EmptyState title={t("No videos yet")} description={t("Upload a recording to start the video processing pipeline.")} action={<Link className="button button-secondary button-small" to="/videos">{t("Open video library")}</Link>}/> : <div className="recent-list">{videos.slice(0, 5).map((video) => <div className="recent-row" key={video.id}><div className="recent-file-icon"><Film size={17}/></div><div className="recent-main"><strong>{video.name}</strong><small>{video.original_filename} {t("· ")}{formatBytes(video.file_size)}</small></div><StatusBadge status={video.status}/><span className="recent-time">{formatDate(video.created_at)}</span></div>)}</div>}
        </section>
        <section className="panel quick-panel">
          <SectionHeading title={t("Quick actions")} subtitle={t("Common workspace tasks")}/>
          <div className="quick-actions">
            <QuickAction to="/cameras" icon={<Camera size={18}/>} title={t("Register a camera")} text="Add an RTSP or browser source"/>
            <QuickAction to="/videos" icon={<Film size={18}/>} title={t("Upload a recording")} text="Queue a video for frame extraction"/>
            <QuickAction to="/detections" icon={<Radar size={18}/>} title={t("Run AI detection")} text="Analyze extracted video frames"/>
            <QuickAction to="/tracking" icon={<Layers3 size={18}/>} title={t("Run object tracking")} text="Follow detected objects across frames"/>
          </div>
        </section>
      </div>
      <div className="notice notice-info platform-note"><ShieldCheck size={17}/><span><strong>{t("Operational note:")}</strong> {t("processing and detection jobs are queued by the API and executed by Django management commands. Live camera streaming and event automation are planned for upcoming releases.")}</span></div>
    </>}
  </>;
}

function MetricCard({ label, value, meta, icon, tone }: { label: string; value: string | number; meta: string; icon: ReactNode; tone: string }) {
  return <div className="metric-card"><div className="metric-top"><span>{label}</span><div className={`metric-icon metric-${tone}`}>{icon}</div></div><div className="metric-value">{value}</div><div className="metric-meta">{t(meta)}</div></div>;
}
function QuickAction({ to, icon, title, text }: { to: string; icon: ReactNode; title: string; text: string }) {
  return <Link className="quick-action" to={to}><div className="quick-icon">{icon}</div><div><strong>{title}</strong><small>{t(text)}</small></div><ArrowUpRight size={15}/></Link>;
}
