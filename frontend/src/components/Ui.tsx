import { t } from '../i18n';
import { ArrowRight, LoaderCircle, Search, Plus, RefreshCw, Inbox } from 'lucide-react';
import type { ReactNode } from 'react';

export function PageHeader({ eyebrow, title, description, actions }: { eyebrow?: string; title: string; description?: string; actions?: ReactNode }) {
  return <div className="page-header"><div><div className="eyebrow">{t(eyebrow || 'AEGISVISION PLATFORM')}</div><h1>{t(title)}</h1>{description && <p>{t(description)}</p>}</div>{actions && <div className="page-actions">{actions}</div>}</div>;
}
export function Button({ children, variant = 'primary', size = 'normal', disabled, onClick, type = 'button', className = '' }: { children: ReactNode; variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; size?: 'normal' | 'small'; disabled?: boolean; onClick?: () => void; type?: 'button' | 'submit'; className?: string }) {
  return <button type={type} disabled={disabled} onClick={onClick} className={`button button-${variant} button-${size} ${className}`}>{children}</button>;
}
export function LoadingState({ label = 'Loading workspace data…' }: { label?: string }) {
  return <div className="loading-state"><LoaderCircle className="spin" size={22}/><span>{t(label)}</span></div>;
}
export function EmptyState({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return <div className="empty-state"><div className="empty-icon"><Inbox size={23}/></div><h3>{title}</h3><p>{description}</p>{action}</div>;
}
export function SearchInput({ value, onChange, placeholder = 'Search…' }: { value: string; onChange: (value: string) => void; placeholder?: string }) {
  return <label className="search-input"><Search size={16}/><input value={value} onChange={(e) => onChange(e.target.value)} placeholder={t(placeholder)}/></label>;
}
export function RefreshButton({ onClick, loading = false }: { onClick: () => void; loading?: boolean }) {
  return <Button variant="secondary" size="small" onClick={onClick} disabled={loading}><RefreshCw size={15} className={loading ? 'spin' : ''}/> {t("Refresh")}</Button>;
}
export function SectionHeading({ title, subtitle, action }: { title: string; subtitle?: string; action?: ReactNode }) {
  return <div className="section-heading"><div><h2>{t(title)}</h2>{subtitle && <p>{t(subtitle)}</p>}</div>{action}</div>;
}
export function InlineLink({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return <button className="inline-link" onClick={onClick}>{children}<ArrowRight size={14}/></button>;
}
export function FormField({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return <label className="form-field"><span>{t(label)}</span>{children}{hint && <small>{t(hint)}</small>}</label>;
}
export function AddButton({ children, onClick }: { children: ReactNode; onClick: () => void }) {
  return <Button onClick={onClick}><Plus size={16}/>{children}</Button>;
}
