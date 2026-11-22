import { t, useLanguage } from '../i18n';
import type { FormEvent } from 'react';
import { useEffect, useState } from 'react';
import { MailPlus, RefreshCw, Shield, UserMinus, Users } from 'lucide-react';
import { api, describeApiError } from '../lib/api';
import type { Membership, Role } from '../lib/types';
import { formatDate, initials, titleCase } from '../lib/format';
import { useOrganizations } from '../context/OrganizationContext';
import { Button, EmptyState, FormField, LoadingState, PageHeader } from '../components/Ui';
import Modal from '../components/Modal';
import StatusBadge from '../components/StatusBadge';
import { notify } from '../components/Toast';

export default function TeamPage() {
  
  useLanguage();
const { activeOrganization } = useOrganizations();
  const [members, setMembers] = useState<Membership[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [inviteOpen, setInviteOpen] = useState(false);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState<Role>('viewer');
  const [busy, setBusy] = useState(false);
  const refresh = async () => {
    if (!activeOrganization) { setMembers([]); setLoading(false); return; }
    setLoading(true); setError('');
    try { setMembers(await api.get<Membership[]>(`/api/organizations/${activeOrganization.id}/members/`)); }
    catch (err) { setError(describeApiError(err)); }
    finally { setLoading(false); }
  };
  useEffect(() => { void refresh(); }, [activeOrganization?.id]);
  const invite = async (event: FormEvent) => {
    event.preventDefault(); if (!activeOrganization) return;
    setBusy(true); setError('');
    try {
      await api.post(`/api/organizations/${activeOrganization.id}/members/`, { email, role });
      notify('Invitation created', `${email} has been invited as ${role}.`); setInviteOpen(false); setEmail(''); await refresh();
    } catch (err) { setError(describeApiError(err)); }
    finally { setBusy(false); }
  };
  const updateMembership = async (member: Membership, payload: Partial<Pick<Membership, 'role' | 'status'>>) => {
    if (!activeOrganization) return;
    try { await api.patch(`/api/organizations/${activeOrganization.id}/members/${member.id}/`, payload); notify('Membership updated', member.user_email); await refresh(); }
    catch (err) { notify('Could not update membership', describeApiError(err), 'error'); }
  };
  const removeMembership = async (member: Membership) => {
    if (!activeOrganization || !window.confirm(t(`Remove ${member.user_email} from ${activeOrganization.name}?`))) return;
    try { await api.delete(`/api/organizations/${activeOrganization.id}/members/${member.id}/`); notify('Member removed', member.user_email); await refresh(); }
    catch (err) { notify('Could not remove member', describeApiError(err), 'error'); }
  };
  return <>
    <PageHeader eyebrow={t("ACCESS CONTROL / PEOPLE")} title={t("Team & access")} description={t(activeOrganization ? `Manage the people and roles for ${activeOrganization.name}.` : 'Select an organization to manage its members.')} actions={<><Button variant="secondary" onClick={() => void refresh()}><RefreshCw size={16}/> {t("Refresh")}</Button><Button onClick={() => { setError(''); setInviteOpen(true); }}><MailPlus size={16}/> {t("Invite member")}</Button></>}/>
    <div className="role-cards">{[{ role: 'Owner', text: 'Full control and ownership of the organization.', color: 'gold' }, { role: 'Admin', text: 'Manage members, settings, sources, and rules.', color: 'blue' }, { role: 'Operator', text: 'Manage cameras and operational event workflows.', color: 'green' }, { role: 'Analyst / Viewer', text: 'Review analytics or view permitted workspace data.', color: 'violet' }].map((item) => <div className="role-card" key={item.role}><div className={`role-symbol role-${item.color}`}><Shield size={17}/></div><strong>{t(item.role)}</strong><p>{t(item.text)}</p></div>)}</div>
    <section className="panel table-panel"><div className="table-toolbar"><div><h2>{t("Organization members ")}<span className="count-pill">{members.length}</span></h2><p>{t("Invitations are limited to users who already have an AEGISVISION account.")}</p></div></div>
      {loading ? <LoadingState label={t("Loading organization members…")}/> : error ? <div className="notice notice-error">{t(error)}</div> : members.length === 0 ? <EmptyState title={t("No members found")} description={t("You may not have permission to view members, or this workspace has no membership records.")}/> : <div className="table-scroll"><table className="data-table"><thead><tr><th>{t("MEMBER")}</th><th>{t("ROLE")}</th><th>{t("STATUS")}</th><th>{t("JOINED / ADDED")}</th><th>{t("MANAGE ROLE")}</th><th/></tr></thead><tbody>{members.map((member) => <tr key={member.id}><td><div className="table-primary"><div className="avatar avatar-table">{initials(member.user_full_name, member.user_email)}</div><div><strong>{member.user_full_name || t('User')}</strong><small>{member.user_email}</small></div></div></td><td><span className={`role-pill role-pill-${member.role}`}>{t(titleCase(member.role))}</span></td><td><StatusBadge status={member.status}/></td><td>{formatDate(member.joined_at || member.created_at)}</td><td>{member.role === 'owner' ? <span className="muted">{t("Primary owner")}</span> : <select className="table-select" value={member.role} onChange={(e) => void updateMembership(member, { role: e.target.value as Role })}><option value="admin">{t("Admin")}</option><option value="operator">{t("Operator")}</option><option value="analyst">{t("Analyst")}</option><option value="viewer">{t("Viewer")}</option></select>}</td><td>{member.role !== 'owner' && <div className="row-actions">{member.status === 'active' ? <button className="icon-button" title={t("Suspend member")} onClick={() => void updateMembership(member, { status: 'suspended' })}><UserMinus size={15}/></button> : member.status === 'suspended' ? <button className="icon-button" title={t("Reactivate member")} onClick={() => void updateMembership(member, { status: 'active' })}>{t("↻")}</button> : null}<button className="icon-button danger-icon" title={t("Remove member")} onClick={() => void removeMembership(member)}><UserMinus size={15}/></button></div>}</td></tr>)}</tbody></table></div>}
      <div className="table-footer"><span>{members.length} {t("membership records")}</span><span><Shield size={13}/> {t("Role policy enforced by API")}</span></div>
    </section>
    <div className="notice notice-info"><Users size={17}/><span>{t("Ownership transfer is intentionally not exposed in this interface yet. Admin role management is also restricted by the backend's owner/admin policy.")}</span></div>
    {inviteOpen && <Modal title={t("Invite a team member")} subtitle={t("Add an existing AEGISVISION account to this organization.")} onClose={() => setInviteOpen(false)}><form className="modal-form" onSubmit={invite}><FormField label={t("Account email")}><input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("colleague@company.com")}/></FormField><FormField label={t("Organization role")}><select value={role} onChange={(e) => setRole(e.target.value as Role)}><option value="viewer">{t("Viewer")}</option><option value="analyst">{t("Analyst")}</option><option value="operator">{t("Operator")}</option><option value="admin">{t("Admin")}</option></select></FormField><div className="notice notice-warning">{t("The invitee must already have an account. They will receive an invited membership record; email delivery and invitation acceptance UI are not yet integrated into this release.")}</div>{error && <div className="notice notice-error">{t(error)}</div>}<div className="modal-actions"><Button variant="secondary" onClick={() => setInviteOpen(false)}>{t("Cancel")}</Button><Button type="submit" disabled={busy}>{t(busy ? 'Creating…' : 'Create invitation')}</Button></div></form></Modal>}
  </>;
}
