import { t, useLanguage } from '../i18n';
import type { FormEvent } from 'react';
import { useState } from 'react';
import { Building2, Check, Globe2, Plus, RefreshCw, ShieldCheck, Users } from 'lucide-react';
import { api, describeApiError } from '../lib/api';
import { useOrganizations } from '../context/OrganizationContext';
import { AddButton, Button, EmptyState, FormField, PageHeader } from '../components/Ui';
import Modal from '../components/Modal';
import { formatDate } from '../lib/format';
import type { Organization } from '../lib/types';
import { notify } from '../components/Toast';

export default function OrganizationsPage() {
  
  useLanguage();
const { organizations, activeOrganization, setActiveOrganization, refreshOrganizations, loading } = useOrganizations();
  const [modalOpen, setModalOpen] = useState(false);
  const [form, setForm] = useState({ name: '', slug: '', description: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      const created = await api.post<Organization>('/api/organizations/', form);
      setActiveOrganization(created);
      await refreshOrganizations();
      setModalOpen(false); setForm({ name: '', slug: '', description: '' });
      notify('Workspace created', `${created.name} is ready.`);
    } catch (err) { setError(describeApiError(err)); }
    finally { setBusy(false); }
  };
  return <>
    <PageHeader eyebrow={t("WORKSPACE / TENANCY")} title={t("Organizations")} description={t("Manage isolated workspaces, their operational boundaries, and organization-level access.")} actions={<><Button variant="secondary" onClick={() => void refreshOrganizations()}><RefreshCw size={16}/> {t("Refresh")}</Button><AddButton onClick={() => { setError(''); setModalOpen(true); }}>{t("Create workspace")}</AddButton></>}/>
    <div className="organization-banner"><div className="organization-banner-icon"><Globe2 size={23}/></div><div><strong>{t("Multi-tenant workspace model")}</strong><p>{t("Each organization has its own camera inventory, video assets, processing jobs, and AI analysis results.")}</p></div><div className="organization-banner-count"><strong>{organizations.length}</strong><span>{t("Workspaces")}</span></div></div>
    {loading ? <div className="panel"><div className="loading-state">{t("Loading organizations…")}</div></div> : organizations.length === 0 ? <EmptyState title={t("No organizations yet")} description={t("Create your first organization to start adding cameras and managing video assets.")} action={<Button onClick={() => setModalOpen(true)}><Plus size={16}/> {t("Create workspace")}</Button>}/> : <div className="organization-grid">{organizations.map((org) => <article className={`organization-card ${org.id === activeOrganization?.id ? 'organization-active' : ''}`} key={org.id}><div className="organization-card-top"><div className="organization-card-icon"><Building2 size={21}/></div>{org.id === activeOrganization?.id && <span className="active-workspace"><Check size={13}/> {t("ACTIVE")}</span>}</div><h3>{org.name}</h3><p>{t(org.description || 'No description provided for this workspace.')}</p><div className="organization-card-meta"><span><Users size={14}/>{org.member_count ?? '—'} {t("members")}</span><span><ShieldCheck size={14}/>{t(org.is_active ? 'Active' : 'Inactive')}</span></div><div className="organization-card-footer"><div><small>{t("CREATED")}</small><strong>{formatDate(org.created_at)}</strong></div>{org.id === activeOrganization?.id ? <Button variant="secondary" size="small" disabled>{t("Current workspace")}</Button> : <Button size="small" variant="secondary" onClick={() => { setActiveOrganization(org); notify('Workspace switched', org.name); }}>{t("Switch workspace")}</Button>}</div></article>)}</div>}
    <div className="notice notice-info"><ShieldCheck size={17}/><span>{t("Workspace access is enforced by the backend on every organization-scoped API request. The active workspace selector only changes the organization context used by the interface.")}</span></div>
    {modalOpen && <Modal title={t("Create organization")} subtitle={t("Create an isolated workspace for a site, facility, or operating group.")} onClose={() => setModalOpen(false)}><form className="modal-form" onSubmit={submit}><FormField label={t("Organization name")}><input required maxLength={150} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder={t("North Industrial Facility")}/></FormField><FormField label={t("Unique workspace slug")} hint={t("Lowercase letters, numbers, and hyphens.")}><input required maxLength={150} pattern="[a-z0-9]+(?:-[a-z0-9]+)*" value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value.toLowerCase().replace(/\s+/g, '-') })} placeholder={t("north-industrial-facility")}/></FormField><FormField label={t("Description")}><textarea rows={3} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder={t("Purpose and operational scope…")}/></FormField>{error && <div className="notice notice-error">{t(error)}</div>}<div className="modal-actions"><Button variant="secondary" onClick={() => setModalOpen(false)}>{t("Cancel")}</Button><Button type="submit" disabled={busy}>{t(busy ? 'Creating…' : 'Create workspace')}</Button></div></form></Modal>}
  </>;
}
