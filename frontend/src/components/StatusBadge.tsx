import { t, useLanguage } from '../i18n';
import { titleCase } from '../lib/format';
export default function StatusBadge({ status }: { status?: string | null }) {
  
  useLanguage();
const normalized = (status || 'unknown').toLowerCase();
  return <span className={`status-badge status-${normalized}`}><i />{t(titleCase(normalized))}</span>;
}
