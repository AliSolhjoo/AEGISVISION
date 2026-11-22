import { t, useLanguage } from './i18n';
import { Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { OrganizationProvider } from './context/OrganizationContext';
import AppLayout from './components/AppLayout';
import { ToastViewport } from './components/Toast';
import LoginPage from './pages/LoginPage';
import ResetPasswordPage from './pages/ResetPasswordPage';
import OverviewPage from './pages/OverviewPage';
import CamerasPage from './pages/CamerasPage';
import LiveCamerasPage from './pages/LiveCamerasPage';
import VideosPage from './pages/VideosPage';
import DetectionsPage from './pages/DetectionsPage';
import VideoAnalysisPage from './pages/VideoAnalysisPage';
import TrackingPage from './pages/TrackingPage';
import OrganizationsPage from './pages/OrganizationsPage';
import TeamPage from './pages/TeamPage';
import SettingsPage from './pages/SettingsPage';
import MonitoringPage from './pages/MonitoringPage';
import EventsPage from './pages/EventsPage';
import SOCPage from './pages/SOCPage';
import HelpPage from './pages/HelpPage';
import { LoadingState } from './components/Ui';

function AuthenticatedRoutes() {
  const { ready, authenticated } = useAuth();
  if (!ready) return <div className="app-loading"><LoadingState label={t("Securing your session…")}/></div>;
  if (!authenticated) return <Routes><Route path="/login" element={<LoginPage/>}/><Route path="/reset-password" element={<ResetPasswordPage/>}/><Route path="*" element={<Navigate to="/login" replace/>}/></Routes>;
  return <OrganizationProvider><Routes><Route element={<AppLayout/>}>
    <Route index element={<OverviewPage/>}/>
    <Route path="monitoring" element={<MonitoringPage/>}/>
    <Route path="cameras" element={<CamerasPage/>}/>
    <Route path="live-cameras" element={<LiveCamerasPage/>}/>
    <Route path="videos" element={<VideosPage/>}/>
    <Route path="detections" element={<VideoAnalysisPage/>}/>
    <Route path="detection-runs" element={<DetectionsPage/>}/>
    <Route path="tracking" element={<TrackingPage/>}/>
    <Route path="organizations" element={<OrganizationsPage/>}/>
    <Route path="team" element={<TeamPage/>}/>
    <Route path="events" element={<EventsPage/>}/>
    <Route path="soc" element={<SOCPage/>}/>
    <Route path="settings" element={<SettingsPage/>}/>
    <Route path="help" element={<HelpPage/>}/>
    <Route path="*" element={<Navigate to="/" replace/>}/>
  </Route></Routes></OrganizationProvider>;
}

export default function App() {
  
  useLanguage();
return <AuthProvider><AuthenticatedRoutes/><ToastViewport/></AuthProvider>;
}
