import { getLanguage } from '../i18n';

export function formatDate(value?: string | null) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  const locale = getLanguage() === 'fa' ? 'fa-IR-u-ca-persian' : 'en-US';
  return new Intl.DateTimeFormat(locale, {
    month: 'short', day: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
  }).format(date);
}

export function formatRelative(value?: string | null) {
  if (!value) return getLanguage() === 'fa' ? 'هرگز' : 'Never';
  const diff = Date.now() - new Date(value).getTime();
  if (!Number.isFinite(diff)) return '—';
  const minutes = Math.max(0, Math.floor(diff / 60000));
  const fa = getLanguage() === 'fa';
  const number = (n: number) => n.toLocaleString(fa ? 'fa-IR' : 'en-US');
  if (minutes < 1) return fa ? 'همین حالا' : 'Just now';
  if (minutes < 60) return fa ? `${number(minutes)} دقیقه پیش` : `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return fa ? `${number(hours)} ساعت پیش` : `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return fa ? `${number(days)} روز پیش` : `${days}d ago`;
}

function localNumber(value: number, maximumFractionDigits = 1) {
  return new Intl.NumberFormat(getLanguage() === 'fa' ? 'fa-IR' : 'en-US', { maximumFractionDigits }).format(value);
}

export function formatBytes(bytes?: number | null) {
  if (bytes == null || !Number.isFinite(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let size = bytes / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index += 1; }
  return `${localNumber(size, size >= 10 ? 0 : 1)} ${units[index]}`;
}

export function formatDuration(seconds?: number | null) {
  if (seconds == null || !Number.isFinite(seconds)) return '—';
  const total = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  const formatted = hours ? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}` : `${minutes}:${String(secs).padStart(2, '0')}`;
  return getLanguage() === 'fa' ? formatted.replace(/[0-9]/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)]) : formatted;
}

export function titleCase(value?: string | null) {
  if (!value) return 'Unknown';
  return value.replaceAll('_', ' ').replaceAll('-', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function initials(name?: string, email?: string) {
  const source = name?.trim() || email?.split('@')[0] || 'AV';
  return source.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('') || 'AV';
}
