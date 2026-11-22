import { t, useLanguage } from '../i18n';
import type { ReactNode } from 'react';
import type { FormEvent } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, FileVideo, Film, HardDrive, Play, RefreshCw, UploadCloud } from 'lucide-react';
import { api, describeApiError } from '../lib/api';
import type { Camera, VideoAsset } from '../lib/types';
import { formatBytes, formatDate, formatDuration } from '../lib/format';
import { useOrganizations } from '../context/OrganizationContext';
import { AddButton, Button, EmptyState, FormField, LoadingState, PageHeader, SearchInput } from '../components/Ui';
import StatusBadge from '../components/StatusBadge';
import Modal from '../components/Modal';
import { notify } from '../components/Toast';

export default function VideosPage() {
  
  useLanguage();
const { activeOrganization } = useOrganizations();
  const navigate = useNavigate();
  const [videos, setVideos] = useState<VideoAsset[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('all');
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [name, setName] = useState('');
  const [cameraId, setCameraId] = useState('');
  const [interval, setInterval] = useState('1');
  const [maxFrames, setMaxFrames] = useState('300');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = async () => {
    if (!activeOrganization) { setVideos([]); setCameras([]); setLoading(false); return; }
    setLoading(true); setError('');
    try {
      const [videoData, cameraData] = await Promise.all([
        api.get<VideoAsset[]>(`/api/organizations/${activeOrganization.id}/videos/`),
        api.get<Camera[]>(`/api/organizations/${activeOrganization.id}/cameras/`),
      ]);
      setVideos(videoData); setCameras(cameraData);
    } catch (err) { setError(describeApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, [activeOrganization?.id]);
  const filtered = useMemo(() => videos.filter((video) => {
    const matchesSearch = [video.name, video.original_filename].join(' ').toLowerCase().includes(search.toLowerCase());
    const matchesStatus = filter === 'all' || video.status === filter;
    return matchesSearch && matchesStatus;
  }), [videos, search, filter]);

  const upload = async (event: FormEvent) => {
    event.preventDefault(); if (!activeOrganization || !selectedFile) return;
    setBusy(true); setError('');
    const data = new FormData();
    data.append('video', selectedFile);
    data.append('organization_id', activeOrganization.id);
    if (name.trim()) data.append('name', name.trim());
    if (cameraId) data.append('camera_id', cameraId);
    data.append('frame_interval_seconds', interval);
    data.append('max_frames', maxFrames);
    try {
      const result = await api.post<{ asset_id: number }>('/api/video-analysis/upload/', data);
      notify('Automatic analysis started', 'Frame extraction, AI detection, SORT tracking and video rendering are running in the background.');
      setModalOpen(false); setSelectedFile(null); setName(''); setCameraId('');
      await refresh();
      navigate(`/detections?asset_id=${result.asset_id}`);
    } catch (err) { setError(describeApiError(err)); }
    finally { setBusy(false); }
  };
  const reprocess = async (video: VideoAsset) => {
    try {
      await api.post(`/api/video-analysis/assets/${video.id}/start/`, {});
      navigate(`/detections?asset_id=${video.id}`);
    } catch (err) { notify('Cannot start video analysis', describeApiError(err), 'error'); }
  };
  const totalBytes = videos.reduce((sum, video) => sum + video.file_size, 0);

  return <>
    <PageHeader eyebrow={t("MEDIA / INGESTION PIPELINE")} title={t("Video library")} description={t("Upload recordings, track extraction jobs, and prepare assets for AI analysis.")} actions={<><Button variant="secondary" onClick={() => void refresh()}><RefreshCw size={16}/> {t("Refresh")}</Button><AddButton onClick={() => { setError(''); setModalOpen(true); }}>{t("Upload video")}</AddButton></>}/>
    <div className="metric-grid metric-grid-compact">
      <MiniMetric label={t("Total recordings")} value={videos.length} icon={<Film size={17}/>} />
      <MiniMetric label={t("Completed")} value={videos.filter((video) => video.status === 'completed').length} icon={<FileVideo size={17}/>} tone="green"/>
      <MiniMetric label={t("In processing queue")} value={videos.filter((video) => ['queued', 'processing'].includes(video.status)).length} icon={<Play size={17}/>} tone="amber"/>
      <MiniMetric label={t("Storage represented")} value={formatBytes(totalBytes)} icon={<HardDrive size={17}/>} tone="violet"/>
    </div>
    <section className="panel table-panel">
      <div className="table-toolbar video-toolbar"><div><h2>{t("Recorded assets ")}<span className="count-pill">{videos.length}</span></h2><p>{t("Uploaded source files and processing state.")}</p></div><div className="toolbar-controls"><SearchInput value={search} onChange={setSearch} placeholder={t("Search video assets…")}/><select className="filter-select" value={filter} onChange={(e) => setFilter(e.target.value)}><option value="all">{t("All statuses")}</option><option value="queued">{t("Queued")}</option><option value="processing">{t("Processing")}</option><option value="completed">{t("Completed")}</option><option value="failed">{t("Failed")}</option></select></div></div>
      {loading ? <LoadingState label={t("Loading video library…")}/> : error && videos.length === 0 ? <div className="notice notice-error">{t(error)}</div> : filtered.length === 0 ? <EmptyState title={t(search || filter !== 'all' ? 'No matching recordings' : 'Your video library is empty')} description={t("Upload an MP4, MOV, MKV, AVI, or WEBM recording to start extracting frames.")} action={<Button onClick={() => setModalOpen(true)}><UploadCloud size={16}/> {t("Upload first video")}</Button>}/> : <div className="video-grid">{filtered.map((video) => <VideoCard key={video.id} video={video} onReprocess={() => void reprocess(video)}/>)}</div>}
      <div className="table-footer"><span>{filtered.length} {t("assets shown")}</span><span><i className="pulse-dot"/> {t("Max upload size: 250 MB")}</span></div>
    </section>
    <div className="notice notice-info"><Play size={17}/><span>{t("Every new upload starts the complete AI pipeline automatically in the background. Open AI analysis to watch progress and play the rendered result.")}</span></div>
    {modalOpen && <Modal title={t("Upload video asset")} subtitle={t("Upload once. The full AI analysis starts automatically in the background.")} onClose={() => setModalOpen(false)}>
      <form onSubmit={upload} className="modal-form">
        <label className={`file-drop ${selectedFile ? 'file-drop-selected' : ''}`}><input type="file" accept=".mp4,.mov,.mkv,.avi,.webm,video/*" onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}/><div className="file-drop-icon"><UploadCloud size={24}/></div><strong>{selectedFile ? selectedFile.name : t('Choose a video file')}</strong><span>{selectedFile ? `${formatBytes(selectedFile.size)} · ${selectedFile.type || t('Video file')}` : t('MP4, MOV, MKV, AVI or WEBM · up to 250 MB')}</span></label>
        <FormField label={t("Display name (optional)")}><input maxLength={150} value={name} onChange={(e) => setName(e.target.value)} placeholder={t("Loading bay recording")}/></FormField>
        <FormField label={t("Related camera (optional)")}><select value={cameraId} onChange={(e) => setCameraId(e.target.value)}><option value="">{t("No camera association")}</option>{cameras.filter((camera) => camera.is_enabled).map((camera) => <option key={camera.id} value={camera.id}>{camera.name} {t("· ")}{camera.code}</option>)}</select></FormField>
        <div className="form-row"><FormField label={t("Frame interval (seconds)")} hint={t("1–60 seconds")}><input type="number" min="1" max="60" required value={interval} onChange={(e) => setInterval(e.target.value)}/></FormField><FormField label={t("Maximum frames")} hint={t("2–300 frames")}><input type="number" min="2" max="300" required value={maxFrames} onChange={(e) => setMaxFrames(e.target.value)}/></FormField></div>
        {error && <div className="notice notice-error">{t(error)}</div>}
        <div className="modal-actions"><Button variant="secondary" onClick={() => setModalOpen(false)}>{t("Cancel")}</Button><Button type="submit" disabled={busy || !selectedFile}>{t(busy ? 'Uploading…' : 'Upload & analyze automatically')}<ArrowRight size={16}/></Button></div>
      </form>
    </Modal>}
  </>;
}
function MiniMetric({ label, value, icon, tone = 'blue' }: { label: string; value: string | number; icon: ReactNode; tone?: string }) {
  return <div className="mini-metric"><div className={`metric-icon metric-${tone}`}>{icon}</div><div><strong>{value}</strong><span>{label}</span></div></div>;
}
function VideoCard({ video, onReprocess }: { video: VideoAsset; onReprocess: () => void }) {
  return <article className="video-card">
    <div className="video-card-preview"><div className="video-preview-grid"/><div className="video-preview-symbol"><Film size={30}/></div><span className="video-duration">{formatDuration(video.duration_seconds)}</span><span className="video-id">{t("ASSET #")}{video.id}</span></div>
    <div className="video-card-content"><div className="video-card-title"><div><h3>{video.name}</h3><p>{video.original_filename}</p></div><StatusBadge status={video.status}/></div>
      <div className="video-meta-grid"><div><small>{t("FILE SIZE")}</small><strong>{formatBytes(video.file_size)}</strong></div><div><small>{t("RESOLUTION")}</small><strong>{video.width && video.height ? `${video.width} × ${video.height}` : t('Pending')}</strong></div><div><small>{t("EXTRACTED")}</small><strong>{video.frames_count ?? 0} {t("frames")}</strong></div></div>
      {video.processing_job?.error_message && <div className="video-error-text">{video.processing_job.error_message}</div>}
      <div className="video-card-bottom"><span>{formatDate(video.created_at)}</span><div><button className="inline-link" onClick={onReprocess}>{t("Open AI analysis ")}<ArrowRight size={13}/></button><span className="mini-id">{t("ID ")}{video.id}</span></div></div>
      {video.processing_job?.status === 'queued' && <div className="job-hint">{t("Queued for automatic AI analysis.")}</div>}
    </div>
  </article>;
}
