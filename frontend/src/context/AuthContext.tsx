import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { apiRequest, clearTokens, getAccessToken, getRefreshToken, saveTokens } from '../lib/api';
import type { Tokens, User } from '../lib/types';

interface AuthContextValue {
  user: User | null;
  ready: boolean;
  authenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; first_name: string; last_name: string; password: string; password_confirm: string }) => Promise<void>;
  logout: () => Promise<void>;
  clearLocalSession: () => void;
  reloadUser: () => Promise<void>;
  updateUser: (payload: Partial<Pick<User, 'first_name' | 'last_name'>>) => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  const reloadUser = useCallback(async () => {
    if (!getAccessToken() && !getRefreshToken()) {
      setUser(null);
      return;
    }
    const profile = await apiRequest<User>('/api/auth/me/');
    setUser(profile);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await apiRequest<Tokens>('/api/auth/token/', {
      method: 'POST',
      auth: false,
      body: JSON.stringify({ email: email.trim().toLowerCase(), password }),
    });
    saveTokens(result);
    if (result.user) setUser(result.user);
    else await reloadUser();
  }, [reloadUser]);

  const register = useCallback(async (payload: { email: string; first_name: string; last_name: string; password: string; password_confirm: string }) => {
    await apiRequest('/api/auth/register/', {
      method: 'POST',
      auth: false,
      body: JSON.stringify(payload),
    });
  }, []);

  const logout = useCallback(async () => {
    let refresh = getRefreshToken();
    try {
      if (refresh && getAccessToken()) {
        try {
          await apiRequest('/api/auth/logout/', {
            method: 'POST',
            body: JSON.stringify({ refresh }),
            retryAuth: false,
          });
        } catch {
          // If the access token expired, rotate first and blacklist the new refresh token.
          const rotated = await apiRequest<{ access: string; refresh?: string }>(
            '/api/auth/token/refresh/',
            {
              method: 'POST',
              auth: false,
              retryAuth: false,
              body: JSON.stringify({ refresh }),
            },
          );
          saveTokens({ access: rotated.access, refresh: rotated.refresh || refresh });
          refresh = rotated.refresh || refresh;
          await apiRequest('/api/auth/logout/', {
            method: 'POST',
            body: JSON.stringify({ refresh }),
            retryAuth: false,
          });
        }
      }
    } finally {
      clearTokens();
      setUser(null);
    }
  }, []);

  const clearLocalSession = useCallback(() => {
    clearTokens();
    setUser(null);
  }, []);

  const updateUser = useCallback(async (payload: Partial<Pick<User, 'first_name' | 'last_name'>>) => {
    const updated = await apiRequest<User>('/api/auth/me/', {
      method: 'PATCH',
      body: JSON.stringify(payload),
    });
    setUser(updated);
  }, []);

  useEffect(() => {
    let mounted = true;
    const onExpired = () => {
      if (mounted) setUser(null);
    };
    window.addEventListener('aegis:session-expired', onExpired);
    (async () => {
      try {
        if (getAccessToken() || getRefreshToken()) await reloadUser();
      } catch {
        clearTokens();
        if (mounted) setUser(null);
      } finally {
        if (mounted) setReady(true);
      }
    })();
    return () => {
      mounted = false;
      window.removeEventListener('aegis:session-expired', onExpired);
    };
  }, [reloadUser]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    ready,
    authenticated: Boolean(user && getAccessToken()),
    login,
    register,
    logout,
    clearLocalSession,
    reloadUser,
    updateUser,
  }), [user, ready, login, register, logout, clearLocalSession, reloadUser, updateUser]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used within AuthProvider');
  return value;
}
