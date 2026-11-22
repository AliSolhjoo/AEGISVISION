import { t, useLanguage } from '../i18n';
import { useEffect, useState } from 'react';
import { ImageOff, LoaderCircle } from 'lucide-react';
import { api } from '../lib/api';

export default function AuthenticatedImage({ src, alt, className = '' }: { src: string; alt: string; className?: string }) {
  
  useLanguage();
const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let active = true;
    let localUrl: string | null = null;
    setFailed(false);
    setObjectUrl(null);
    api.blob(src).then((blob) => {
      if (!active) return;
      localUrl = URL.createObjectURL(blob);
      setObjectUrl(localUrl);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; if (localUrl) URL.revokeObjectURL(localUrl); };
  }, [src]);
  if (failed) return <div className={`image-fallback ${className}`}><ImageOff size={20}/><span>{t("Image unavailable")}</span></div>;
  if (!objectUrl) return <div className={`image-fallback ${className}`}><LoaderCircle className="spin" size={20}/><span>{t("Loading frame")}</span></div>;
  return <img className={className} src={objectUrl} alt={alt}/>;
}
