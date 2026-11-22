import { t, useLanguage } from '../i18n';
import { useEffect, useState } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

type ToastMessage = { id: number; title: string; description?: string; tone: 'success' | 'error' | 'info' };
let nextId = 1;
export function notify(title: string, description?: string, tone: ToastMessage['tone'] = 'success') {
  window.dispatchEvent(new CustomEvent('aegis:toast', { detail: { id: nextId++, title, description, tone } }));
}

export function ToastViewport() {
  
  useLanguage();
const [items, setItems] = useState<ToastMessage[]>([]);
  useEffect(() => {
    const onToast = (event: Event) => {
      const detail = (event as CustomEvent<ToastMessage>).detail;
      setItems((current) => [...current, detail]);
      window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== detail.id)), 4500);
    };
    window.addEventListener('aegis:toast', onToast);
    return () => window.removeEventListener('aegis:toast', onToast);
  }, []);
  return <div className="toast-viewport">{items.map((item) => {
    const Icon = item.tone === 'success' ? CheckCircle2 : item.tone === 'error' ? AlertCircle : Info;
    return <div className={`toast toast-${item.tone}`} key={item.id}>
      <Icon size={19} />
      <div className="toast-copy"><strong>{t(item.title)}</strong>{item.description && <span>{t(item.description)}</span>}</div>
      <button className="icon-button toast-close" onClick={() => setItems((current) => current.filter((x) => x.id !== item.id))} aria-label={t("Dismiss")}><X size={15} /></button>
    </div>;
  })}</div>;
}
