import { t, LanguageSwitcher, useLanguage } from '../i18n';
import type { FormEvent } from 'react';
import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Activity, ArrowRight, Eye, EyeOff, Fingerprint, LockKeyhole, Mail, ShieldCheck, Sparkles } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { api, describeApiError } from '../lib/api';
import { notify } from '../components/Toast';
import { FormField } from '../components/Ui';

export default function LoginPage() {
  
  useLanguage();
const { login, register } = useAuth();
  const [searchParams] = useSearchParams();
  const [mode, setMode] = useState<'login' | 'register' | 'forgot'>('login');
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ email: '', first_name: '', last_name: '', password: '', password_confirm: '' });
  const navigate = useNavigate();
  const [message, setMessage] = useState('');

  const update = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));
  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setMessage('');
    try {
      if (mode === 'login') {
        await login(form.email, form.password);
        notify('Welcome back', 'Your workspace is ready.');
        navigate('/', { replace: true });
      } else if (mode === 'register') {
        await register(form);
        await login(form.email, form.password);
        notify('Account created', 'Your AEGISVISION account is ready.');
        navigate('/', { replace: true });
      } else {
        await api.publicPost('/api/auth/password-reset/', { email: form.email });
        setMessage('If an active account exists for this email, reset instructions have been sent. In local development, check the Django runserver terminal.');
      }
    } catch (error) {
      const msg = describeApiError(error);
      setMessage(msg);
      notify('Could not complete request', msg, 'error');
    } finally { setBusy(false); }
  };

  const { uid, token } = Object.fromEntries(searchParams.entries());
  return <div className="auth-screen">
    <div className="auth-art">
      <div className="auth-art-grid"/>
      <div className="auth-art-content">
        <div className="brand-lockup auth-brand"><div className="brand-mark"><ShieldCheck size={23}/></div><div><strong>{t("AEGIS")}<span>{t("VISION")}</span></strong><small>{t("VIDEO INTELLIGENCE")}</small></div></div>
        <div className="auth-hero-copy"><div className="eyebrow eyebrow-light"><Sparkles size={13}/> {t("INTELLIGENCE THAT WATCHES OVER WHAT MATTERS")}</div><h1>{t("See beyond")}<br/><em>{t("the frame.")}</em></h1><p>{t("Turn video into actionable intelligence with an integrated platform for computer vision, monitoring, and operational awareness.")}</p></div>
        <div className="auth-feature-strip"><div><Activity size={18}/><span>{t("Real-time insights")}</span></div><div><Fingerprint size={18}/><span>{t("Secure by design")}</span></div><div><LockKeyhole size={18}/><span>{t("Organization isolation")}</span></div></div>
        <div className="auth-art-footer"><span>{t("AEGISVISION PLATFORM")}</span><span>{t("BUILT FOR OPERATIONAL CLARITY")}</span></div>
      </div>
      <div className="orb orb-one"/><div className="orb orb-two"/>
    </div>
    <div className="auth-panel">
      <div className="auth-language-row"><LanguageSwitcher/></div>
      <div className="auth-mobile-brand"><div className="brand-mark"><ShieldCheck size={22}/></div><strong>{t("AEGIS")}<span>{t("VISION")}</span></strong></div>
      <div className="auth-form-wrap">
        <div className="auth-kicker">{t(mode === 'login' ? 'SECURE ACCESS' : mode === 'register' ? 'CREATE YOUR ACCOUNT' : 'ACCOUNT RECOVERY')}</div>
        <h2>{t(mode === 'login' ? 'Welcome back' : mode === 'register' ? 'Create your account' : 'Reset your password')}</h2>
        <p className="auth-subtitle">{t(mode === 'login' ? 'Sign in to continue to your intelligence workspace.' : mode === 'register' ? 'Start building a clearer picture of your operations.' : 'Enter your email and we will send recovery instructions if an active account exists.')}</p>
        {uid && token && <div className="notice notice-info">{t("A password reset link was detected. Use the reset form on the dedicated reset page after setting your password from the link.")}</div>}
        <form onSubmit={handleSubmit} className="auth-form">
          {mode === 'register' && <div className="form-row"><FormField label={t("First name")}><input required value={form.first_name} onChange={(e) => update('first_name', e.target.value)} placeholder={t("Alex")}/></FormField><FormField label={t("Last name")}><input required value={form.last_name} onChange={(e) => update('last_name', e.target.value)} placeholder={t("Morgan")}/></FormField></div>}
          <FormField label={t("Email address")}><div className="input-with-icon"><Mail size={17}/><input type="email" required autoComplete="email" value={form.email} onChange={(e) => update('email', e.target.value)} placeholder={t("you@company.com")}/></div></FormField>
          {mode !== 'forgot' && <FormField label={t("Password")}><div className="input-with-icon"><LockKeyhole size={17}/><input type={showPassword ? 'text' : 'password'} required minLength={mode === 'register' ? 8 : undefined} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} value={form.password} onChange={(e) => update('password', e.target.value)} placeholder={t("Enter your password")}/><button className="input-action" type="button" onClick={() => setShowPassword((v) => !v)} aria-label={t("Toggle password visibility")}>{showPassword ? <EyeOff size={17}/> : <Eye size={17}/>}</button></div></FormField>}
          {mode === 'register' && <FormField label={t("Confirm password")}><div className="input-with-icon"><LockKeyhole size={17}/><input type="password" required minLength={8} value={form.password_confirm} onChange={(e) => update('password_confirm', e.target.value)} placeholder={t("Repeat your password")}/></div></FormField>}
          {mode === 'login' && <div className="auth-form-meta"><span><i className="tiny-check"/> {t("Protected session")}</span><button type="button" onClick={() => { setMode('forgot'); setMessage(''); }}>{t("Forgot password?")}</button></div>}
          {message && <div className="notice notice-info">{t(message)}</div>}
          <button className="button button-primary auth-submit" disabled={busy} type="submit">{t(busy ? 'Please wait…' : mode === 'login' ? 'Sign in to workspace' : mode === 'register' ? 'Create account' : 'Send recovery instructions')}<ArrowRight size={17}/></button>
        </form>
        <div className="auth-switch">{mode === 'login' ? <>{t("New to AEGISVISION? ")}<button onClick={() => { setMode('register'); setMessage(''); }}>{t("Create an account")}</button></> : mode === 'register' ? <>{t("Already have an account? ")}<button onClick={() => { setMode('login'); setMessage(''); }}>{t("Sign in")}</button></> : <>{t("Remembered your password? ")}<button onClick={() => { setMode('login'); setMessage(''); }}>{t("Back to sign in")}</button></>}</div>
        <div className="auth-security"><ShieldCheck size={15}/> {t("Your session is protected with signed access tokens.")}</div>
      </div>
      <div className="auth-panel-footer"><span>{t("© ")}{new Date().getFullYear()} {t("AEGISVISION")}</span><span>{t("PRIVACY · SECURITY · STATUS")}</span></div>
    </div>
  </div>;
}
