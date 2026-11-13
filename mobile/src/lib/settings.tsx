import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export type ThemeChoice = 'system' | 'light' | 'dark';

export interface Settings {
  consent: boolean;
  theme: ThemeChoice;
  name: string;
  anonymous: boolean;
  hidePoint: boolean;
  favorites: string[];
  onIce: { active: boolean; until: string | null; contact: string };
}

const DEFAULTS: Settings = {
  consent: false,
  theme: 'system',
  name: '',
  anonymous: true,
  hidePoint: true,
  favorites: [],
  onIce: { active: false, until: null, contact: '' },
};
const KEY = 'kl.settings';

const Ctx = createContext<{
  settings: Settings;
  ready: boolean;
  update: (patch: Partial<Settings>) => void;
}>({ settings: DEFAULTS, ready: false, update: () => {} });

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(DEFAULTS);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((raw) => raw && setSettings({ ...DEFAULTS, ...JSON.parse(raw) }))
      .catch(() => undefined)
      .finally(() => setReady(true));
  }, []);

  const update = useCallback((patch: Partial<Settings>) => {
    setSettings((s) => {
      const next = { ...s, ...patch };
      AsyncStorage.setItem(KEY, JSON.stringify(next)).catch(() => undefined);
      return next;
    });
  }, []);

  const value = useMemo(() => ({ settings, ready, update }), [settings, ready, update]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useSettings = () => useContext(Ctx);

/** Minutes left until the planned return; negative when late. null when the mode is off. */
export function onIceLeftMs(s: Settings, now = Date.now()): number | null {
  if (!s.onIce.active || !s.onIce.until) return null;
  return new Date(s.onIce.until).getTime() - now;
}
