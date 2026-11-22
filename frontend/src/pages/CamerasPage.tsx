import { t, useLanguage } from '../i18n';
import type { ReactNode } from 'react';
import type { FormEvent } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Camera as CameraIcon, Pencil, Plus, Radio, ShieldCheck, Trash2, Wifi, WifiOff } from 'lucide-react';
import type { Camera } from '../lib/types';
import { api, describeApiError } from '../lib/api';
import { formatDate, titleCase } from '../lib/format';
import { useOrganizations } from '../context/OrganizationContext';
import { AddButton, Button, EmptyState, FormField, LoadingState, PageHeader, SearchInput } from '../components/Ui';
import StatusBadge from '../components/StatusBadge';
import Modal from '../components/Modal';
import { notify } from '../components/Toast';

type CameraForm = { name: string; code: string; description: string; location: string; source_type: Camera['source_type']; stream_url: string; stream_username: string; stream_password: string; target_fps: number; confidence_threshold: number; clear_credentials: boolean };
const initialForm: CameraForm = { name: '', code: '', description: '', location: '', source_type: 'rtsp', stream_url: '', stream_username: '', stream_password: '', target_fps: 2, confidence_threshold: 0.55, clear_credentials: false };

export default function CamerasPage() {
  
  useLanguage();
const { activeOrganization } = useOrganizations();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<Camera | null>(null);
  const [form, setForm] = useState<CameraForm>(initialForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const refresh = async () => {
    if (!activeOrganization) { setCameras([]); setLoading(false); return; }
    setLoading(true); setError('');
    try { setCameras(await api.get<Camera[]>(`/api/organizations/${activeOrganization.id}/cameras/`)); }
    catch (err) { setError(describeApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, [activeOrganization?.id]);
  const filtered = useMemo(() => cameras.filter((camera) => [camera.name, camera.code, camera.location, camera.source_type, camera.status].join(' ').toLowerCase().includes(search.toLowerCase())), [cameras, search]);
  const openCreate = () => { setEditing(null); setForm(initialForm); setError(''); setModalOpen(true); };
  const openEdit = (camera: Camera) => { setEditing(camera); setForm({ ...initialForm, name: camera.name, code: camera.code, description: camera.description || '', location: camera.location || '', source_type: camera.source_type, target_fps: camera.target_fps || 2, confidence_threshold: camera.confidence_threshold ?? 0.55 }); setError(''); setModalOpen(true); };
  const submit = async (event: FormEvent) => {
    event.preventDefault(); if (!activeOrganization) return;
    setSaving(true); setError('');
    const payload: Record<string, string | number | boolean> = { name: form.name, code: form.code, description: form.description, location: form.location, source_type: form.source_type, target_fps: form.target_fps, confidence_threshold: form.confidence_threshold, clear_credentials: form.clear_credentials };
    if (form.source_type !== 'browser' && form.stream_url.trim()) payload.stream_url = form.stream_url.trim();
    if (form.source_type === 'browser') payload.stream_url = '';
    if (form.stream_username.trim() || form.stream_password) { payload.stream_username = form.stream_username.trim(); payload.stream_password = form.stream_password; }
    try {
      if (editing) await api.patch(`/api/organizations/${activeOrganization.id}/cameras/${editing.id}/`, payload);
      else await api.post(`/api/organizations/${activeOrganization.id}/cameras/`, payload);
      notify(editing ? 'Camera updated' : 'Camera registered', `${form.name} is saved to this workspace.`);
      setModalOpen(false); await refresh();
    } catch (err) { setError(describeApiError(err)); }
    finally { setSaving(false); }
  };
  const disableCamera = async (camera: Camera) => {
    if (!activeOrganization || !window.confirm(t(`Disable camera “${camera.name}”? The record will be retained.`))) return;
    try { await api.delete(`/api/organizations/${activeOrganization.id}/cameras/${camera.id}/`); notify('Camera disabled', camera.name); await refresh(); }
    catch (err) { notify('Could not disable camera', describeApiError(err), 'error'); }
  };

  return <>
    <PageHeader eyebrow={t("SOURCES / CAMERA INVENTORY")} title={t("Camera management")} description={t("Register and organize the video sources connected to your operational environment.")} actions={<><Button variant="secondary" onClick={() => void refresh()}><Radio size={16}/> {t("Refresh")}</Button><AddButton onClick={openCreate}>{t("Add camera")}</AddButton></>}/>
    <div className="metric-grid metric-grid-compact">
      <MiniMetric label={t("Total sources")} value={cameras.length} icon={<CameraIcon size={17}/>} />
      <MiniMetric label={t("Online")} value={cameras.filter((camera) => camera.status === 'online' && camera.is_enabled).length} icon={<Wifi size={17}/>} tone="green" />
      <MiniMetric label={t("Offline / Error")} value={cameras.filter((camera) => ['offline', 'error'].includes(camera.status) && camera.is_enabled).length} icon={<WifiOff size={17}/>} tone="red" />
      <MiniMetric label={t("Disabled")} value={cameras.filter((camera) => !camera.is_enabled).length} icon={<ShieldCheck size={17}/>} tone="muted" />
    </div>
    <section className="panel table-panel">
      <div className="table-toolbar"><div><h2>{t("Registered sources ")}<span className="count-pill">{cameras.length}</span></h2><p>{t("Sources belong to the currently selected organization.")}</p></div><SearchInput value={search} onChange={setSearch} placeholder={t("Search cameras…")}/></div>
      {loading ? <LoadingState label={t("Loading camera inventory…")}/> : error ? <div className="notice notice-error">{t(error)}</div> : filtered.length === 0 ? <EmptyState title={t(search ? 'No matching cameras' : 'No cameras registered')} description={t(search ? 'Try another search term.' : 'Add an RTSP or RTSPS network camera source to this organization.')} action={!search && <Button onClick={openCreate}><Plus size={16}/> {t("Register first camera")}</Button>}/> : <div className="table-scroll"><table className="data-table"><thead><tr><th>{t("CAMERA SOURCE")}</th><th>{t("LOCATION")}</th><th>{t("TYPE")}</th><th>{t("STATUS")}</th><th>{t("LAST SEEN")}</th><th>{t("CREATED")}</th><th/></tr></thead><tbody>{filtered.map((camera) => <tr key={camera.id}>
        <td><div className="table-primary"><div className="table-icon camera-table-icon"><CameraIcon size={17}/></div><div><strong>{camera.name}</strong><small>{camera.code}</small></div></div></td>
        <td>{camera.location || <span className="muted">{t("Not specified")}</span>}</td><td><span className="type-chip">{t(titleCase(camera.source_type))}</span></td><td><StatusBadge status={camera.is_enabled ? camera.status : 'disabled'}/></td><td>{camera.last_seen_at ? formatDate(camera.last_seen_at) : <span className="muted">{t("Not reported")}</span>}</td><td>{formatDate(camera.created_at)}</td>
        <td><div className="row-actions"><button className="icon-button" title={t("Edit camera")} onClick={() => openEdit(camera)} disabled={!camera.is_enabled}><Pencil size={15}/></button><button className="icon-button danger-icon" title={t("Disable camera")} onClick={() => void disableCamera(camera)} disabled={!camera.is_enabled}><Trash2 size={15}/></button></div></td>
      </tr>)}</tbody></table></div>}
      <div className="table-footer"><span>{t("Showing ")}{filtered.length} {t("of ")}{cameras.length} {t("sources")}</span><span><i className="pulse-dot"/> {t("Organization-scoped inventory")}</span></div>
    </section>
    <div className="notice notice-info"><ShieldCheck size={17}/><span>{t("RTSP credentials are encrypted at rest and never returned by the API. Start the live-camera worker from the AEGISVISION launcher to enable live analysis. Browser sources are not processed by the server-side RTSP worker.")}</span></div>
    {modalOpen && <Modal title={t(editing ? 'Edit camera source' : 'Register camera source')} subtitle={t("Register an RTSP/RTSPS network camera for server-side live AI analysis.")} onClose={() => setModalOpen(false)}>
      <form onSubmit={submit} className="modal-form">
        <div className="form-row"><FormField label={t("Camera name")}><input required maxLength={120} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("North entrance camera")}/></FormField><FormField label={t("Unique code")}><input required maxLength={64} value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value.toLowerCase().replace(/[^a-z0-9]+/g, '-') })} placeholder={t("north-entrance")}/></FormField></div>
        <div className="form-row"><FormField label={t("Source type")}><select value={form.source_type} onChange={(e) => setForm({ ...form, source_type: e.target.value as Camera['source_type'], stream_url: '' })}><option value="rtsp">{t("RTSP network camera")}</option><option value="rtsps">{t("RTSPS secure stream")}</option><option value="browser">{t("Browser camera")}</option></select></FormField><FormField label={t("Location")}><input maxLength={180} value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} placeholder={t("Building A · North gate")}/></FormField></div>
        {form.source_type !== 'browser' && <FormField label={t("Stream URL")} hint={t("Enter the camera RTSP address without username or password. Network query parameters are allowed; do not put secret tokens in them.")}><input required={!editing || editing.source_type !== form.source_type} value={form.stream_url} onChange={(e) => setForm({ ...form, stream_url: e.target.value })} placeholder={`${form.source_type}://192.168.10.20:554/stream1`}/></FormField>}
        {form.source_type !== 'browser' && <div className="form-row"><FormField label={t("RTSP username")} hint={editing && editing.has_stream_credentials ? t("Credentials are already stored securely. Leave both fields empty to keep them.") : t("Optional camera login username.")}><input autoComplete="off" value={form.stream_username} onChange={(e) => setForm({ ...form, stream_username: e.target.value, clear_credentials: false })} placeholder={t("Camera username")}/></FormField><FormField label={t("RTSP password")}><input type="password" autoComplete="new-password" value={form.stream_password} onChange={(e) => setForm({ ...form, stream_password: e.target.value, clear_credentials: false })} placeholder={t("Camera password")}/></FormField></div>}
        <div className="form-row"><FormField label={t("AI inference FPS")} hint={t("Maximum analysis rate. Higher values require more CPU/GPU resources.")}><select value={form.target_fps} onChange={(e) => setForm({ ...form, target_fps: Number(e.target.value) })}>{[1,2,3,4,5,8,10].map((value) => <option key={value} value={value}>{value} FPS</option>)}</select></FormField><FormField label={t("Detection confidence")}><select value={form.confidence_threshold} onChange={(e) => setForm({ ...form, confidence_threshold: Number(e.target.value) })}>{[0.35,0.45,0.55,0.65,0.75,0.85].map((value) => <option key={value} value={value}>{Math.round(value*100)}%</option>)}</select></FormField></div>
        {editing?.has_stream_credentials && <label className="checkbox-line"><input type="checkbox" checked={form.clear_credentials} onChange={(e) => setForm({ ...form, clear_credentials: e.target.checked, stream_username: '', stream_password: '' })}/>{t("Remove saved camera credentials")}</label>}
        <FormField label={t("Description")}><textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder={t("Coverage area and operational notes…")}/></FormField>
        {error && <div className="notice notice-error">{t(error)}</div>}
        <div className="modal-actions"><Button variant="secondary" onClick={() => setModalOpen(false)}>{t("Cancel")}</Button><Button type="submit" disabled={saving}>{t(saving ? 'Saving…' : editing ? 'Save changes' : 'Register camera')}</Button></div>
      </form>
    </Modal>}
  </>;
}
function MiniMetric({ label, value, icon, tone = 'blue' }: { label: string; value: number; icon: ReactNode; tone?: string }) {
  return <div className="mini-metric"><div className={`metric-icon metric-${tone}`}>{icon}</div><div><strong>{value}</strong><span>{label}</span></div></div>;
}
