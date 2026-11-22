import { t, useLanguage } from '../i18n';
import { useEffect } from 'react';
import type { ReactNode } from 'react';
import { X } from 'lucide-react';

export default function Modal({ title, subtitle, onClose, children, size = 'medium' }: {
  title: string; subtitle?: string; onClose: () => void; children: ReactNode; size?: 'medium' | 'large';
}) {
  
  useLanguage();
useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  return <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <section className={`modal modal-${size}`} role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal-head"><div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div><button className="icon-button" onClick={onClose} aria-label={t("Close")}><X size={18} /></button></div>
      <div className="modal-body">{children}</div>
    </section>
  </div>;
}
