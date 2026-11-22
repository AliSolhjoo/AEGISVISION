import { t, useLanguage } from '../i18n';
import type { FormEvent } from 'react';
import { useState } from 'react';
import { Check, KeyRound, LockKeyhole, Mail, Save, ShieldCheck, UserRound } from 'lucide-react';
import { api, describeApiError } from '../lib/api';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import { Button, FormField, PageHeader } from '../components/Ui';
import { initials, formatDate } from '../lib/format';
import { notify } from '../components/Toast';

export default function SettingsPage() {
  
  useLanguage();
const { user, updateUser, clearLocalSession } = useAuth();
  const navigate = useNavigate();
  const [profile, setProfile] = useState({ first_name: user?.first_name || '', last_name: user?.last_name || '' });
  const [password, setPassword] = useState({ current_password: '', new_password: '', new_password_confirm: '' });
  const [profileBusy, setProfileBusy] = useState(false);
  const [passwordBusy, setPasswordBusy] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const saveProfile = async (event: FormEvent) => {
    event.preventDefault(); setProfileBusy(true); setProfileError('');
    try { await updateUser(profile); notify('Profile updated', 'Your account details have been saved.'); }
    catch (err) { setProfileError(describeApiError(err)); }
    finally { setProfileBusy(false); }
  };
  const changePassword = async (event: FormEvent) => {
    event.preventDefault(); setPasswordBusy(true); setPasswordError('');
    try {
      await api.post('/api/auth/change-password/', password);
      notify('Password changed', 'Please sign in again with your new password.');
      clearLocalSession();
      navigate('/login', { replace: true });
    } catch (err) { setPasswordError(describeApiError(err)); }
    finally { setPasswordBusy(false); }
  };
  return <>
    <PageHeader eyebrow={t("ACCOUNT / SECURITY")} title={t("Account settings")} description={t("Manage your identity, sign-in security, and personal account preferences.")}/>
    <div className="settings-layout">
      <div className="settings-main">
        <section className="panel settings-panel"><div className="settings-title"><div className="settings-title-icon"><UserRound size={18}/></div><div><h2>{t("Profile information")}</h2><p>{t("Update the name displayed across your workspace.")}</p></div></div>
          <form className="settings-form" onSubmit={saveProfile}><div className="profile-summary"><div className="avatar avatar-profile">{initials(user?.full_name, user?.email)}</div><div><strong>{user?.full_name || user?.email}</strong><span>{user?.email}</span></div><span className="verified-label"><ShieldCheck size={13}/> {t("Account")}</span></div>
            <div className="form-row"><FormField label={t("First name")}><input value={profile.first_name} onChange={(e) => setProfile({ ...profile, first_name: e.target.value })} maxLength={150}/></FormField><FormField label={t("Last name")}><input value={profile.last_name} onChange={(e) => setProfile({ ...profile, last_name: e.target.value })} maxLength={150}/></FormField></div>
            <FormField label={t("Email address")}><div className="input-with-icon input-disabled"><Mail size={16}/><input value={user?.email || ''} disabled/><span className="locked-indicator">{t("Verified")}</span></div></FormField>
            {profileError && <div className="notice notice-error">{t(profileError)}</div>}<div className="settings-submit"><span className="form-footnote">{t("Member since ")}{formatDate(user?.date_joined)}</span><Button type="submit" disabled={profileBusy}><Save size={15}/>{t(profileBusy ? 'Saving…' : 'Save profile')}</Button></div>
          </form>
        </section>
        <section className="panel settings-panel"><div className="settings-title"><div className="settings-title-icon settings-title-warn"><KeyRound size={18}/></div><div><h2>{t("Change password")}</h2><p>{t("Choose a strong password that you do not use elsewhere.")}</p></div></div>
          <form className="settings-form" onSubmit={changePassword}><FormField label={t("Current password")}><input type="password" required autoComplete="current-password" value={password.current_password} onChange={(e) => setPassword({ ...password, current_password: e.target.value })}/></FormField><div className="form-row"><FormField label={t("New password")}><input type="password" required minLength={8} autoComplete="new-password" value={password.new_password} onChange={(e) => setPassword({ ...password, new_password: e.target.value })}/></FormField><FormField label={t("Confirm new password")}><input type="password" required minLength={8} autoComplete="new-password" value={password.new_password_confirm} onChange={(e) => setPassword({ ...password, new_password_confirm: e.target.value })}/></FormField></div>
            <div className="password-guidance"><LockKeyhole size={15}/><span>{t("Use at least 8 characters, and avoid common or numeric-only passwords. Django’s password validators will enforce the configured policy.")}</span></div>
            {passwordError && <div className="notice notice-error">{t(passwordError)}</div>}<div className="settings-submit"><span className="form-footnote">{t("Changing your password will invalidate existing refresh tokens.")}</span><Button type="submit" disabled={passwordBusy}>{t(passwordBusy ? 'Updating…' : 'Update password')}</Button></div>
          </form>
        </section>
      </div>
      <aside className="settings-side"><div className="panel security-card"><div className="security-card-icon"><ShieldCheck size={24}/></div><h3>{t("Security overview")}</h3><p>{t("Your account uses signed JWT access tokens and organization-scoped API permissions.")}</p><div className="security-line"><span>{t("Access token lifetime")}</span><strong>{t("10 minutes")}</strong></div><div className="security-line"><span>{t("Refresh token lifetime")}</span><strong>{t("7 days")}</strong></div><div className="security-line"><span>{t("Token rotation")}</span><strong className="positive"><Check size={13}/> {t("Enabled")}</strong></div><div className="security-line"><span>{t("Refresh blacklist")}</span><strong className="positive"><Check size={13}/> {t("Enabled")}</strong></div></div>
      <div className="panel help-card"><div className="help-card-icon"><KeyRound size={18}/></div><strong>{t("Need account recovery?")}</strong><p>{t("Request a password reset link if you can’t access your account.")}</p><button className="text-link" onClick={async () => { try { await api.publicPost('/api/auth/password-reset/', { email: user?.email }); notify('Recovery request accepted', 'If the account is active, instructions were sent. Check the Django terminal in local development.'); } catch (err) { notify('Recovery request failed', describeApiError(err), 'error'); } }}>{t("Send recovery email ")}<span>{t("→")}</span></button></div></aside>
    </div>
  </>;
}
