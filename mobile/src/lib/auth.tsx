import * as SecureStore from 'expo-secure-store';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { api, ApiError, setAuthToken } from './api';
import { flushQueue } from './queue';
import type { User } from './types';

const TOKEN_KEY = 'kl.token';
const USER_KEY = 'kl.user';

interface AuthCtx {
  user: User | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string, name: string) => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx>({
  user: null,
  ready: false,
  login: async () => {},
  register: async () => {},
  logout: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const token = await SecureStore.getItemAsync(TOKEN_KEY);
        const cached = await SecureStore.getItemAsync(USER_KEY);
        if (token) {
          setAuthToken(token);
          if (cached) setUser(JSON.parse(cached));
          // refresh the profile; a 401 means the token expired
          api
            .me()
            .then((u) => {
              setUser(u);
              SecureStore.setItemAsync(USER_KEY, JSON.stringify(u)).catch(() => undefined);
            })
            .catch(async (e) => {
              if (e instanceof ApiError && e.status === 401) {
                setAuthToken(null);
                setUser(null);
                await SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => undefined);
              }
            });
        }
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const save = useCallback(async (token: string, u: User) => {
    setAuthToken(token);
    setUser(u);
    await SecureStore.setItemAsync(TOKEN_KEY, token);
    await SecureStore.setItemAsync(USER_KEY, JSON.stringify(u));
    flushQueue().catch(() => undefined);
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const r = await api.login(email, password);
      await save(r.token, r.user);
    },
    [save],
  );

  const register = useCallback(
    async (email: string, password: string, name: string) => {
      const r = await api.register({ email, password, display_name: name, website: '' }); // website: anti-bot trap
      await save(r.token, r.user);
    },
    [save],
  );

  const logout = useCallback(async () => {
    await api.logout().catch(() => undefined);
    setAuthToken(null);
    setUser(null);
    await SecureStore.deleteItemAsync(TOKEN_KEY).catch(() => undefined);
    await SecureStore.deleteItemAsync(USER_KEY).catch(() => undefined);
  }, []);

  const value = useMemo(() => ({ user, ready, login, register, logout }), [user, ready, login, register, logout]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useAuth = () => useContext(Ctx);
