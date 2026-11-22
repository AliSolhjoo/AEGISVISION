import { t, LanguageSwitcher, useLanguage } from '../i18n';
import type { FormEvent } from 'react';
import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, KeyRound, ShieldCheck } from 'lucide-react';
import { api, describeApiError } from '../lib/api';
import { Button, FormField } from '../components/Ui';
import { notify } from '../components/Toast';

export default function ResetPasswordPage() {
  
  useLanguage();
const [params] = useSearchParams();
  const uid = params.get('uid') || '';
  const token = params.get('token') || '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);
  const navigate = useNavigate();
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('');
    try {
      await api.publicPost('/api/auth/password-reset/confirm/', { uid, token, new_password: password, new_password_confirm: confirm });
      setDone(true); notify('Password reset', 'You can now sign in with your new password.');
    } catch (err) { setError(describeApiError(err)); }
    finally { setBusy(false); }
  };
  return <div className="reset-screen"><div className="reset-card"><div className="reset-language-row"><LanguageSwitcher/></div><div className="brand-lockup auth-brand"><div className="brand-mark"><ShieldCheck size={22}/></div><div><strong>{t("AEGIS")}<span>{t("VISION")}</span></strong><small>{t("VIDEO INTELLIGENCE")}</small></div></div>
    {!uid || !token ? <><div className="reset-icon"><KeyRound size={23}/></div><h1>{t("Invalid reset link")}</h1><p>{t("The password reset link is missing required information. Request a new recovery email.")}</p><Link className="button button-primary" to="/login">{t("Back to sign in")}</Link></> : done ? <><div className="reset-icon reset-icon-success"><ShieldCheck size={23}/></div><h1>{t("Password updated")}</h1><p>{t("Your password has been changed. Your previous refresh sessions have been revoked.")}</p><Button onClick={() => navigate('/login')}>{t("Continue to sign in")}</Button></> : <><div className="auth-kicker">{t("ACCOUNT RECOVERY")}</div><h1>{t("Choose a new password")}</h1><p>{t("Set a strong password for your AEGISVISION account.")}</p><form onSubmit={submit} className="modal-form"><FormField label={t("New password")}><input type="password" required minLength={8} autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)}/></FormField><FormField label={t("Confirm new password")}><input type="password" required minLength={8} autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)}/></FormField>{error && <div className="notice notice-error">{t(error)}</div>}<Button type="submit" disabled={busy} className="button-block">{t(busy ? 'Updating…' : 'Reset password')}</Button></form></>}
    <Link className="reset-back" to="/login"><ArrowLeft size={14}/> {t("Return to sign in")}</Link>
  </div></div>;
}
