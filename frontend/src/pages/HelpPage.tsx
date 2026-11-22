import { t, useLanguage } from '../i18n';
import { BookOpen, Code2, GitBranch, LifeBuoy, Server, TerminalSquare } from 'lucide-react';
import { PageHeader } from '../components/Ui';

export default function HelpPage() {
  
  useLanguage();
return <><PageHeader eyebrow={t("DOCUMENTATION / OPERATIONS")} title={t("Help center")} description={t("Quick operational guidance for running the AEGISVISION development environment.")}/><div className="help-grid">
    <section className="panel help-doc-card"><div className="help-doc-icon"><Server size={20}/></div><h3>{t("Start the backend")}</h3><p>{t("Open a terminal in the backend directory and run the Django development server.")}</p><pre>python manage.py runserver</pre><small>{t("Default API: http://127.0.0.1:8000")}</small></section>
    <section className="panel help-doc-card"><div className="help-doc-icon"><TerminalSquare size={20}/></div><h3>{t("Process uploaded videos")}</h3><p>{t("Upload creates a queued processing job. Run the worker command to extract frames.")}</p><pre>python manage.py process_videos --limit 1</pre><small>{t("Execute from the backend directory.")}</small></section>
    <section className="panel help-doc-card"><div className="help-doc-icon"><Code2 size={20}/></div><h3>{t("Run AI detection")}</h3><p>{t("Queue a detection run from the AI detections page, then execute the detector command.")}</p><pre>python manage.py detect_video_objects --limit 1</pre><small>{t("First model execution may download pretrained weights.")}</small></section>
    <section className="panel help-doc-card"><div className="help-doc-icon"><GitBranch size={20}/></div><h3>{t("Run object tracking")}</h3><p>{t("Queue a tracking run after object detection, then execute the tracking worker command.")}</p><pre>python manage.py track_video_objects --limit 1</pre><small>{t("Execute from the backend directory.")}</small></section>
    <section className="panel help-doc-card"><div className="help-doc-icon"><BookOpen size={20}/></div><h3>{t("Frontend development")}</h3><p>{t("The frontend uses Vite proxying for API calls, so local development does not require editing Django CORS settings.")}</p><pre>npm install{`\n`}npm run dev</pre><small>{t("Default frontend: http://localhost:5173")}</small></section>
  </div><section className="panel help-support"><LifeBuoy size={20}/><div><strong>{t("API integration note")}</strong><p>{t("The UI consumes the existing Django REST endpoints. Features that do not yet have backend APIs are clearly marked as planned rather than shown with fabricated data.")}</p></div></section></>;
}
