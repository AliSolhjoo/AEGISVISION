import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { api } from '../lib/api';
import type { Organization } from '../lib/types';
import { useAuth } from './AuthContext';

interface OrganizationContextValue {
  organizations: Organization[];
  activeOrganization: Organization | null;
  setActiveOrganization: (organization: Organization) => void;
  refreshOrganizations: () => Promise<void>;
  loading: boolean;
}
const OrganizationContext = createContext<OrganizationContextValue | null>(null);
const STORAGE_KEY = 'aegisvision.organization';

export function OrganizationProvider({ children }: { children: ReactNode }) {
  const { authenticated } = useAuth();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [activeOrganization, setActive] = useState<Organization | null>(null);
  const [loading, setLoading] = useState(false);

  const setActiveOrganization = useCallback((organization: Organization) => {
    setActive(organization);
    sessionStorage.setItem(STORAGE_KEY, organization.id);
  }, []);

  const refreshOrganizations = useCallback(async () => {
    if (!authenticated) { setOrganizations([]); setActive(null); return; }
    setLoading(true);
    try {
      const result = await api.get<Organization[]>('/api/organizations/');
      setOrganizations(result);
      const selectedId = sessionStorage.getItem(STORAGE_KEY);
      const selected = result.find((item) => item.id === selectedId) || result[0] || null;
      setActive(selected);
      if (selected) sessionStorage.setItem(STORAGE_KEY, selected.id);
      else sessionStorage.removeItem(STORAGE_KEY);
    } finally {
      setLoading(false);
    }
  }, [authenticated]);

  useEffect(() => {
    void refreshOrganizations().catch(() => { setOrganizations([]); setActive(null); });
  }, [refreshOrganizations]);

  const value = useMemo(() => ({ organizations, activeOrganization, setActiveOrganization, refreshOrganizations, loading }), [organizations, activeOrganization, setActiveOrganization, refreshOrganizations, loading]);
  return <OrganizationContext.Provider value={value}>{children}</OrganizationContext.Provider>;
}

export function useOrganizations() {
  const value = useContext(OrganizationContext);
  if (!value) throw new Error('useOrganizations must be used within OrganizationProvider');
  return value;
}
