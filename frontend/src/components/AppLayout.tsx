import { t, LanguageSwitcher, useLanguage } from '../i18n';
import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, Bell, Camera, ChevronDown, CircleHelp, Cpu, Film, LayoutDashboard,
  LogOut, Menu, Network, Settings, ShieldCheck, Users, Video, X, Zap, GitBranch, Siren,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useOrganizations } from '../context/OrganizationContext';
import { initials } from '../lib/format';
import { api } from '../lib/api';

const navGroups = [
  { label: 'WORKSPACE', items: [
    { to: '/', label: 'Overview', icon: LayoutDashboard },
    { to: '/monitoring', label: 'Monitoring', icon: Video },
    { to: '/live-cameras', label: 'Live camera intelligence', icon: Activity },
    { to: '/cameras', label: 'Cameras', icon: Camera },
    { to: '/videos', label: 'Video library', icon: Film },
    { to: '/detections', label: 'Automatic analysis', icon: Cpu },
    { to: '/tracking', label: 'Object tracking', icon: GitBranch },
  ] },
  { label: 'MANAGEMENT', items: [
    { to: '/organizations', label: 'Organizations', icon: Network },
    { to: '/team', label: 'Team & access', icon: Users },
    { to: '/soc', label: 'Security Operations Center', icon: Siren },
    { to: '/events', label: 'Events & alerts', icon: Bell },
  ] },
  { label: 'ACCOUNT', items: [
    { to: '/settings', label: 'Settings', icon: Settings },
    { to: '/help', label: 'Help center', icon: CircleHelp },
  ] },
];

const titleMap: Record<string, string> = {
  '/': 'Overview', '/monitoring': 'Live monitoring', '/cameras': 'Camera management', '/live-cameras': 'Live camera intelligence',
  '/videos': 'Video library', '/detections': 'Automatic video analysis', '/tracking': 'Object tracking', '/organizations': 'Organizations',
  '/team': 'Team & access', '/events': 'Events & alerts', '/soc': 'Security Operations Center', '/settings': 'Account settings', '/help': 'Help center',
};

export default function AppLayout() {
  
  useLanguage();
const [mobileOpen, setMobileOpen] = useState(false);
  const [orgOpen, setOrgOpen] = useState(false);
  const [openIncidentCount, setOpenIncidentCount] = useState(0);
  const { user, logout } = useAuth();
  const { organizations, activeOrganization, setActiveOrganization } = useOrganizations();
  const location = useLocation();
  const navigate = useNavigate();
  const title = t(titleMap[location.pathname] || 'AEGISVISION');

  useEffect(() => {
    if (!activeOrganization) { setOpenIncidentCount(0); return; }
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.get<{ summary: { open_events: number } }>(`/api/organizations/${activeOrganization.id}/soc/dashboard/`);
        if (!cancelled) setOpenIncidentCount(data.summary.open_events || 0);
      } catch { if (!cancelled) setOpenIncidentCount(0); }
    };
    void load();
    const timer = window.setInterval(() => { if (!document.hidden) void load(); }, 30000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [activeOrganization?.id]);

  const sidebar = <>
    <div className="brand-lockup">
      <div className="brand-mark"><ShieldCheck size={22}/></div>
      <div><strong>{t("AEGIS")}<span>{t("VISION")}</span></strong><small>{t("VIDEO INTELLIGENCE")}</small></div>
      {mobileOpen && <button className="icon-button sidebar-close" onClick={() => setMobileOpen(false)}><X size={18}/></button>}
    </div>
    <div className="workspace-select-wrap">
      <button className="workspace-select" onClick={() => setOrgOpen((v) => !v)}>
        <div className="workspace-avatar"><Network size={16}/></div>
        <div className="workspace-name"><small>{t("ACTIVE WORKSPACE")}</small><strong>{activeOrganization?.name || t('No workspace')}</strong></div>
        <ChevronDown size={16} className={orgOpen ? 'rotate' : ''}/>
      </button>
      {orgOpen && <div className="workspace-menu">
        {organizations.map((org) => <button key={org.id} className={org.id === activeOrganization?.id ? 'selected' : ''} onClick={() => { setActiveOrganization(org); setOrgOpen(false); setMobileOpen(false); }}>
          <span className="org-dot"/><span>{org.name}</span>{org.id === activeOrganization?.id && <span className="menu-check">{t("✓")}</span>}
        </button>)}
        <NavLink to="/organizations" onClick={() => { setOrgOpen(false); setMobileOpen(false); }}>{t("+ Manage workspaces")}</NavLink>
      </div>}
    </div>
    <nav className="sidebar-nav">
      {navGroups.map((group) => <div className="nav-group" key={group.label}>
        <div className="nav-group-label">{t(group.label)}</div>
        {group.items.map(({ to, label, icon: Icon }) => <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => `nav-link ${isActive ? 'active' : ''}`} onClick={() => setMobileOpen(false)}>
          <Icon size={18}/><span>{t(label)}</span>
        </NavLink>)}
      </div>)}
    </nav>
    <div className="sidebar-bottom">
      <div className="system-status"><span className="pulse-dot"/><div><strong>{t("Platform connected")}</strong><small>{t("API session active")}</small></div></div>
      <div className="sidebar-user">
        <div className="avatar">{initials(user?.full_name, user?.email)}</div>
        <div className="sidebar-user-info"><strong>{user?.full_name || user?.email}</strong><small>{user?.email}</small></div>
        <button className="icon-button" title={t("Sign out")} onClick={() => void logout().catch(() => undefined)}><LogOut size={17}/></button>
      </div>
    </div>
  </>;

  return <div className="app-shell">
    <aside className="sidebar">{sidebar}</aside>
    {mobileOpen && <div className="mobile-scrim" onClick={() => setMobileOpen(false)} />}
    {mobileOpen && <aside className="sidebar mobile-sidebar">{sidebar}</aside>}
    <main className="main-area">
      <header className="topbar">
        <div className="topbar-left">
          <button className="icon-button mobile-menu-button" onClick={() => setMobileOpen(true)} aria-label={t("Open menu")}><Menu size={20}/></button>
          <div className="breadcrumb"><span>{t("Workspace")}</span><span className="crumb-separator">{t("/")}</span><strong>{title}</strong></div>
        </div>
        <div className="topbar-right">
          <LanguageSwitcher/>
          <div className="topbar-time"><span className="pulse-dot"/>{t("SYSTEM ONLINE")}</div>
          <button className="topbar-icon topbar-alert-button" title={t("Security Operations Center")} aria-label={t("Security Operations Center")} onClick={() => navigate('/soc')}><Bell size={18}/>{openIncidentCount > 0 && <span className="topbar-alert-count">{openIncidentCount > 99 ? "99+" : openIncidentCount}</span>}</button>
          <div className="topbar-divider"/>
          <NavLink to="/settings" className="topbar-profile"><div className="avatar avatar-small">{initials(user?.full_name, user?.email)}</div><ChevronDown size={14}/></NavLink>
        </div>
      </header>
      <div className="page-container"><Outlet/></div>
      <footer className="app-footer"><span>{t("© ")}{new Date().getFullYear()} {t("AEGISVISION")}</span><span><Zap size={12}/> {t("AI-powered video intelligence")}</span><span>{t("Platform v1.5.0")}</span></footer>
    </main>
  </div>;
}
