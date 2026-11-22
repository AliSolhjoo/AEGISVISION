import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { Activity, CheckCircle2, Download, FileVideo2, Film, Loader2, PlayCircle, UploadCloud, XCircle } from 'lucide-react';
import { useOrganizations } from '../context/OrganizationContext';
import { api, describeApiError } from '../lib/api';
import type { Camera, VideoAsset } from '../lib/types';
import { useLanguage } from '../i18n';

type AnalysisStatus = {
  asset_id: number;
  asset_name: string;
  status: 'processing' | 'completed' | 'failed';
  phase: string;
  progress: number;
  message: string;
  frames_extracted: number;
  frames_detected: number;
  detections_count: number;
  tracking_run_id: number | null;
  tracks_count: number;
  observations_count: number;
  events_count?: number;
  event_analysis_error?: string;
  result_ready: boolean;
  result_url: string | null;
  error: string;
};

type UploadResponse = { asset_id: number; worker_pid: number; status: string; status_url: string };
type LocalizedText = { fa: string; en: string };

const phaseNames: Record<string, LocalizedText> = {
  queued: { fa: 'در صف پردازش', en: 'Queued for processing' },
  extracting: { fa: 'استخراج فریم‌های ویدئو', en: 'Extracting video frames' },
  detecting: { fa: 'تشخیص اشیا با هوش مصنوعی', en: 'Running AI object detection' },
  tracking: { fa: 'رهگیری اشیا با SORT', en: 'Tracking objects with SORT' },
  event_analysis: { fa: 'تحلیل رویدادهای امنیتی', en: 'Analyzing security events' },
  rendering: { fa: 'ساخت ویدئوی خروجی', en: 'Rendering the annotated video' },
  completed: { fa: 'تحلیل با موفقیت تکمیل شد', en: 'Analysis completed successfully' },
  failed: { fa: 'پردازش با خطا مواجه شد', en: 'Analysis failed' },
};

const videoStatusNames: Record<string, LocalizedText> = {
  queued: { fa: 'در صف', en: 'Queued' },
  processing: { fa: 'در حال پردازش', en: 'Processing' },
  completed: { fa: 'تکمیل‌شده', en: 'Completed' },
  failed: { fa: 'ناموفق', en: 'Failed' },
};

const initialStatus = (assetId: number, assetName: string): AnalysisStatus => ({
  asset_id: assetId,
  asset_name: assetName,
  status: 'processing',
  phase: 'queued',
  progress: 0,
  message: 'Queued for processing',
  frames_extracted: 0,
  frames_detected: 0,
  detections_count: 0,
  tracking_run_id: null,
  tracks_count: 0,
  observations_count: 0,
  result_ready: false,
  result_url: null,
  error: '',
});

const knownPersianErrors: Record<string, string> = {
  'ابتدا یک فایل ویدئویی انتخاب کن.': 'Select a video file first.',
  'ابتدا یک سازمان فعال انتخاب کن.': 'Select an active workspace first.',
  'پردازش ویدئو ناموفق بود.': 'Video processing failed.',
  'فایل خروجی تحلیل پیدا نشد': 'The rendered analysis file could not be found.',
  'تحلیل با خطا متوقف شد': 'Analysis stopped because an error occurred.',
  'برای این ویدئو هنوز هیچ قانون فعالی تعریف نشده است.': 'No active security rules are configured for this video.',
  'رهگیری ویدئو باید قبل از تحلیل رویدادها تکمیل شده باشد.': 'Video tracking must finish before security-event analysis can run.',
};

function containsPersian(value: string) {
  return /[\u0600-\u06FF]/.test(value);
}

export default function VideoAnalysisPage() {
  const { activeOrganization, loading: organizationLoading } = useOrganizations();
  const { language, direction } = useLanguage();
  const fa = language === 'fa';
  const tr = (persian: string, english: string) => fa ? persian : english;
  const [searchParams] = useSearchParams();
  const queryAssetId = useMemo(() => {
    const value = Number(searchParams.get('asset_id'));
    return Number.isSafeInteger(value) && value > 0 ? value : null;
  }, [searchParams]);

  const [file, setFile] = useState<File | null>(null);
  const [libraryVideos, setLibraryVideos] = useState<VideoAsset[]>([]);
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState('');
  const [libraryLoading, setLibraryLoading] = useState(false);
  const [videoName, setVideoName] = useState('');
  const [assetId, setAssetId] = useState<number | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const lastLoadedAsset = useRef<number | null>(null);
  const startRequestedFor = useRef<number | null>(null);

  const localizeServerMessage = (message: string) => {
    if (fa || !message) return message;
    if (knownPersianErrors[message]) return knownPersianErrors[message];
    if (containsPersian(message)) {
      return tr('عملیات با خطا مواجه شد.', 'The operation could not be completed.');
    }
    return message;
  };

  useEffect(() => {
    if (!activeOrganization) {
      setLibraryVideos([]);
      setCameras([]);
      setSelectedCameraId('');
      return;
    }
    let cancelled = false;
    setLibraryLoading(true);
    api.get<VideoAsset[]>(`/api/organizations/${activeOrganization.id}/videos/`)
      .then((items) => { if (!cancelled) setLibraryVideos(items); })
      .catch(() => { if (!cancelled) setLibraryVideos([]); })
      .finally(() => { if (!cancelled) setLibraryLoading(false); });
    api.get<Camera[]>(`/api/organizations/${activeOrganization.id}/cameras/`)
      .then((items) => { if (!cancelled) setCameras(items); })
      .catch(() => { if (!cancelled) setCameras([]); });
    return () => { cancelled = true; };
  }, [activeOrganization?.id]);

  useEffect(() => {
    return () => {
      if (videoUrl) URL.revokeObjectURL(videoUrl);
    };
  }, [videoUrl]);

  // Open an existing video from the library and start/resume the same pipeline.
  useEffect(() => {
    if (!queryAssetId || organizationLoading || !activeOrganization) return;
    if (startRequestedFor.current === queryAssetId) return;
    startRequestedFor.current = queryAssetId;
    setAssetId(queryAssetId);
    setAnalysis(initialStatus(queryAssetId, `Video #${queryAssetId}`));
    setBusy(true);
    setError('');
    setVideoUrl('');
    lastLoadedAsset.current = null;

    api.post<UploadResponse>(`/api/video-analysis/assets/${queryAssetId}/start/`, {})
      .catch((reason: unknown) => {
        if (startRequestedFor.current === queryAssetId) {
          setError(describeApiError(reason));
          setBusy(false);
          setAssetId(null);
        }
      });
  }, [queryAssetId, activeOrganization?.id, organizationLoading]);

  // Poll one asset until the worker has completed all stages and rendered its MP4.
  useEffect(() => {
    if (!assetId) return;
    let cancelled = false;
    let timer: number | undefined;

    const poll = async () => {
      try {
        const payload = await api.get<AnalysisStatus>(`/api/video-analysis/assets/${assetId}/status/`);
        if (cancelled) return;
        setAnalysis(payload);
        setError('');
        setLibraryVideos((current) => current.map((item) => item.id === assetId
          ? {
              ...item,
              status: payload.status,
              frames_count: payload.frames_extracted,
              processing_job: item.processing_job
                ? { ...item.processing_job, frame_count: payload.frames_extracted, status: payload.status }
                : item.processing_job,
            }
          : item));

        if (payload.status === 'failed') {
          setError(payload.error || payload.message || 'Video processing failed.');
          setBusy(false);
          return;
        }

        if (payload.status === 'completed' && payload.result_ready && lastLoadedAsset.current !== assetId) {
          const blob = await api.blob(`/api/video-analysis/assets/${assetId}/result/`);
          if (cancelled) return;
          const objectUrl = URL.createObjectURL(blob);
          setVideoUrl(objectUrl);
          lastLoadedAsset.current = assetId;
          setBusy(false);
          return;
        }

        if (payload.status !== 'completed' || !payload.result_ready) {
          timer = window.setTimeout(poll, 1800);
        }
      } catch (reason) {
        if (!cancelled) {
          setError(describeApiError(reason));
          timer = window.setTimeout(poll, 3500);
        }
      }
    };

    void poll();
    return () => {
      cancelled = true;
      if (timer) window.clearTimeout(timer);
    };
  }, [assetId]);

  async function startExistingVideo(video: VideoAsset) {
    setError('');
    setBusy(true);
    setVideoUrl('');
    lastLoadedAsset.current = null;
    setAssetId(video.id);
    setAnalysis(initialStatus(video.id, video.name));
    try {
      await api.post<UploadResponse>(`/api/video-analysis/assets/${video.id}/start/`, {});
    } catch (reason) {
      setError(describeApiError(reason));
      setBusy(false);
      setAssetId(null);
    }
  }

  async function startAnalysis(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!file) {
      setError(tr('ابتدا یک فایل ویدئویی انتخاب کن.', 'Select a video file first.'));
      return;
    }
    if (!activeOrganization) {
      setError(tr('ابتدا یک سازمان فعال انتخاب کن.', 'Select an active workspace first.'));
      return;
    }

    setBusy(true);
    setError('');
    setAnalysis(null);
    setAssetId(null);
    setVideoUrl('');
    lastLoadedAsset.current = null;

    const form = new FormData();
    form.append('video', file);
    form.append('organization_id', String(activeOrganization.id));
    form.append('frame_interval_seconds', '1');
    form.append('max_frames', '300');
    if (videoName.trim()) form.append('name', videoName.trim());
    if (selectedCameraId) form.append('camera_id', selectedCameraId);

    try {
      const payload = await api.post<UploadResponse>('/api/video-analysis/upload/', form);
      const newId = Number(payload.asset_id);
      setAssetId(newId);
      setAnalysis(initialStatus(newId, videoName.trim() || file.name));
      setFile(null);
      setVideoName('');
      void api.get<VideoAsset[]>(`/api/organizations/${activeOrganization.id}/videos/`).then(setLibraryVideos).catch(() => undefined);
      const input = document.getElementById('automatic-video-input') as HTMLInputElement | null;
      if (input) input.value = '';
    } catch (reason) {
      setError(describeApiError(reason));
      setBusy(false);
    }
  }

  const isWorking = busy || (!!assetId && analysis?.status === 'processing');
  const stats: [string, number | string][] = analysis ? [
    [tr('فریم استخراج‌شده', 'Extracted frames'), analysis.frames_extracted],
    [tr('فریم تحلیل‌شده', 'Frames analyzed'), analysis.frames_detected],
    [tr('اشیای شناسایی‌شده', 'Objects detected'), analysis.detections_count],
    [tr('Trackهای ساخته‌شده', 'Tracks created'), analysis.tracks_count],
    [tr('مشاهدات رهگیری', 'Tracking observations'), analysis.observations_count],
    [tr('رویدادهای امنیتی', 'Security events'), analysis.events_count ?? 0],
    [tr('شناسه اجرای رهگیری', 'Tracking run ID'), analysis.tracking_run_id ?? '—'],
  ] : [];

  const phaseLabel = analysis
    ? (phaseNames[analysis.phase] ? (fa ? phaseNames[analysis.phase].fa : phaseNames[analysis.phase].en) : tr('در حال پردازش', 'Processing'))
    : '';
  const visibleError = error ? localizeServerMessage(error) : '';
  const visibleAnalysisError = analysis?.error ? localizeServerMessage(analysis.error) : '';
  const visibleEventError = analysis?.event_analysis_error ? localizeServerMessage(analysis.event_analysis_error) : '';

  function number(value: number) {
    return value.toLocaleString(fa ? 'fa-IR' : 'en-US');
  }
  function formatVideoStatus(status: string) {
    const value = videoStatusNames[status];
    return value ? (fa ? value.fa : value.en) : status;
  }

  return (
    <main dir={direction} className="auto-analysis-page">
      <div className="auto-analysis-shell">
        <header className="auto-analysis-header">
          <div>
            <div className="auto-analysis-eyebrow">AEGISVISION / AUTOMATIC AI PIPELINE</div>
            <h1>{tr('تحلیل خودکار ویدئو', 'Automatic Video Analysis')}</h1>
            <p>{tr('ویدئو را بارگذاری کن؛ استخراج فریم، تشخیص، رهگیری و ساخت ویدئوی خروجی به‌صورت خودکار در پس‌زمینه انجام می‌شود.', 'Upload a video. Frame extraction, object detection, SORT tracking, event analysis, and annotated video rendering run automatically in the background.')}</p>
          </div>
          <div className="auto-analysis-org"><Activity size={16}/>{activeOrganization?.name || (organizationLoading ? tr('در حال بارگذاری سازمان…', 'Loading workspace…') : tr('سازمانی انتخاب نشده', 'No workspace selected'))}</div>
        </header>

        <section className="auto-analysis-grid">
          <form className="auto-analysis-card" onSubmit={startAnalysis}>
            <div className="auto-analysis-card-title"><UploadCloud size={20}/><h2>{tr('ویدئوی جدید', 'New video')}</h2></div>
            <label className="auto-analysis-field">
              {tr('عنوان ویدئو (اختیاری)', 'Video title (optional)')}
              <input value={videoName} onChange={(event) => setVideoName(event.target.value)} placeholder={tr('مثلاً دوربین ورودی اصلی', 'e.g. Main entrance camera')} disabled={isWorking}/>
            </label>
            <label className="auto-analysis-field">
              {tr('دوربین مرتبط (اختیاری)', 'Associated camera (optional)')}
              <select value={selectedCameraId} onChange={(event) => setSelectedCameraId(event.target.value)} disabled={isWorking}>
                <option value="">{tr('بدون اتصال به دوربین', 'Not linked to a camera')}</option>
                {cameras.filter((camera) => camera.is_enabled).map((camera) => <option key={camera.id} value={camera.id}>{camera.name} · {camera.code}</option>)}
              </select>
            </label>
            <label className={`auto-analysis-drop ${file ? 'has-file' : ''}`} htmlFor="automatic-video-input">
              <FileVideo2 size={34}/>
              <strong>{file ? file.name : tr('انتخاب یا رها کردن فایل ویدئویی', 'Choose or drop a video file')}</strong>
              <span>{file ? `${(file.size / (1024 * 1024)).toFixed(1)} ${tr('مگابایت', 'MB')}` : tr('MP4، MOV، AVI، MKV یا WebM · حداکثر ۲۵۰ مگابایت', 'MP4, MOV, AVI, MKV, or WebM · up to 250 MB')}</span>
              <input id="automatic-video-input" type="file" accept="video/*,.mkv" disabled={isWorking} onChange={(event) => setFile(event.target.files?.[0] || null)}/>
            </label>
            <button className="auto-analysis-submit" type="submit" disabled={!file || !activeOrganization || isWorking}>
              {isWorking ? <><Loader2 size={17} className="auto-spin"/>{tr('در حال تحلیل…', 'Analyzing…')}</> : <><PlayCircle size={17}/>{tr('آپلود و شروع تحلیل خودکار', 'Upload & start automatic analysis')}</>}
            </button>
            <div className="auto-analysis-note">{tr('پس از آپلود، به اجرای هیچ دستور CMD یا انتخاب جداگانه Detection و Tracking نیازی نیست.', 'After upload, no CMD commands or separate Detection/Tracking actions are required.')}</div>
          </form>

          <section className="auto-analysis-card auto-analysis-progress-card">
            <div className="auto-analysis-card-title"><Activity size={20}/><h2>{tr('وضعیت تحلیل', 'Analysis status')}</h2></div>
            {!analysis ? (
              <div className="auto-analysis-empty"><Film size={34}/><span>{tr('پس از آپلود، مراحل پردازش و آمار اینجا نمایش داده می‌شوند.', 'Processing stages and analysis statistics will appear here after upload.')}</span></div>
            ) : (
              <>
                <div className="auto-analysis-progress-head">
                  <strong>{phaseLabel}</strong>
                  <b>{number(analysis.progress)}%</b>
                </div>
                <div className="auto-analysis-progress-track"><div style={{ width: `${Math.max(0, Math.min(100, analysis.progress))}%` }} className={analysis.status === 'failed' ? 'failed' : ''}/></div>
                <div className="auto-analysis-current-video">{analysis.asset_name} <span>{tr('شناسه', 'ID')} #{number(analysis.asset_id)}</span></div>
                <div className="auto-analysis-stats">
                  {stats.map(([label, value]) => <div key={label}><span>{label}</span><strong>{typeof value === 'number' ? number(value) : value}</strong></div>)}
                </div>
                {analysis.status === 'completed' && <div className="auto-analysis-success"><CheckCircle2 size={17}/>{tr('تحلیل کامل شد؛ ویدئوی خروجی آماده پخش است.', 'Analysis is complete. The rendered video is ready to play.')} <Link to={`/events?video_id=${analysis.asset_id}`} className="auto-analysis-event-link">{tr('مشاهده رویدادهای امنیتی', 'View security events')}</Link></div>}
                {visibleEventError && <div className="auto-analysis-warning">{tr('تحلیل رویدادهای امنیتی کامل نشد:', 'Security-event analysis did not complete:')} {visibleEventError}</div>}
                {analysis.status === 'failed' && <div className="auto-analysis-error"><XCircle size={17}/><span>{visibleError || visibleAnalysisError || tr('تحلیل ناموفق بود.', 'Analysis failed.')}</span></div>}
                {analysis.status === 'failed' && (analysis.error || error) && <details className="auto-analysis-technical"><summary>{tr('جزئیات فنی', 'Technical details')}</summary><code>{analysis.error || error}</code></details>}
              </>
            )}
          </section>
        </section>

        <section className="auto-analysis-card auto-analysis-library">
          <div className="auto-analysis-card-title"><Film size={20}/><h2>{tr('ویدئوهای موجود در فضای کاری', 'Videos in this workspace')}</h2></div>
          <p className="auto-analysis-library-description">{tr('ویدئوهای قبلی را هم می‌توانی از همین صفحه تحلیل یا نتیجه آن‌ها را دوباره مشاهده کنی؛ از جمله ویدئوهایی که هنوز در صف پردازش مانده‌اند.', 'You can start or resume analysis for existing videos here, including recordings that are still queued for processing.')}</p>
          {libraryLoading ? <div className="auto-analysis-library-empty"><Loader2 size={17} className="auto-spin"/>{tr('در حال دریافت ویدئوها…', 'Loading videos…')}</div> : libraryVideos.length === 0 ? <div className="auto-analysis-library-empty">{tr('هنوز ویدئویی در کتابخانه این سازمان وجود ندارد.', 'There are no videos in this workspace yet.')}</div> : (
            <div className="auto-analysis-library-list">
              {libraryVideos.map((video) => (
                <article className="auto-analysis-library-row" key={video.id}>
                  <div className="auto-analysis-library-file"><FileVideo2 size={19}/><div><strong>{video.name}</strong><span>{video.original_filename} · #{number(video.id)}</span></div></div>
                  <div className="auto-analysis-library-meta"><span className={`auto-analysis-status status-${video.status}`}>{formatVideoStatus(video.status)}</span><small>{number(video.frames_count ?? video.processing_job?.frame_count ?? 0)} {tr('فریم', 'frames')}</small></div>
                  <button type="button" onClick={() => void startExistingVideo(video)} disabled={isWorking} className="auto-analysis-library-button">{video.status === 'processing' ? tr('مشاهده پیشرفت', 'View progress') : video.status === 'completed' ? tr('مشاهده / تحلیل مجدد', 'View / re-analyze') : tr('شروع تحلیل', 'Start analysis')}<PlayCircle size={15}/></button>
                </article>
              ))}
            </div>
          )}
        </section>

        {visibleError && analysis?.status !== 'failed' && <div className="auto-analysis-error auto-analysis-error-global"><XCircle size={17}/>{visibleError}{containsPersian(error) && !fa && <details className="auto-analysis-technical"><summary>Technical details</summary><code>{error}</code></details>}</div>}

        {videoUrl && analysis?.status === 'completed' && (
          <section className="auto-analysis-card auto-analysis-output">
            <div className="auto-analysis-output-head">
              <div><div className="auto-analysis-eyebrow">ANALYSIS RESULT</div><h2>{tr('ویدئوی تحلیل‌شده', 'Analyzed video')}</h2><p>{tr('کادر اشیا، نام کلاس و Track ID روی ویدئوی اصلی نمایش داده می‌شوند.', 'Object bounding boxes, class labels, and Track IDs are rendered over the original video.')}</p></div>
              <a href={videoUrl} download={`aegisvision-analysis-${assetId}.mp4`}><Download size={16}/>{tr('دریافت ویدئو', 'Download video')}</a>
            </div>
            <video controls playsInline preload="metadata" src={videoUrl}/>
          </section>
        )}
      </div>
    </main>
  );
}
