import AsyncStorage from '@react-native-async-storage/async-storage';

import type {
  Alert,
  NewObservation,
  Observation,
  ReactionKind,
  Weather,
  ZoneCollection,
  ZoneDetail,
} from './types';

// On a phone, localhost is the phone itself: set EXPO_PUBLIC_API_URL=http://<your-computer-ip>:8000
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

const DEVICE_KEY = 'kl.deviceId';
let deviceId: string | null = null;

export async function getDeviceId(): Promise<string> {
  if (deviceId) return deviceId;
  let id = await AsyncStorage.getItem(DEVICE_KEY);
  if (!id) {
    id = 'dev-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
    await AsyncStorage.setItem(DEVICE_KEY, id);
  }
  deviceId = id;
  return id;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

/** True when the request never reached the server (no network, server down). */
export function isNetworkError(e: unknown): boolean {
  return !(e instanceof ApiError);
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set('X-Device-Id', await getDeviceId());
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 15000);
  try {
    const res = await fetch(API_URL + path, { ...init, headers, signal: controller.signal });
    if (!res.ok) {
      let msg = `Ошибка сервера (${res.status})`;
      try {
        const j = await res.json();
        if (typeof j.detail === 'string') msg = j.detail;
        else if (Array.isArray(j.detail) && j.detail[0]?.msg) msg = 'Проверьте поля: ' + j.detail[0].msg;
      } catch {}
      throw new ApiError(res.status, msg);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}

export const photoUrl = (p: string | null) => (p ? API_URL + p : null);

export const api = {
  zones: () => request<ZoneCollection>('/zones'),
  zone: (id: string) => request<ZoneDetail>(`/zones/${encodeURIComponent(id)}`),
  observations: (q: Record<string, string | number | boolean | undefined> = {}) => {
    const qs = Object.entries(q)
      .filter(([, v]) => v !== undefined && v !== false)
      .map(([k, v]) => `${k}=${encodeURIComponent(String(v))}`)
      .join('&');
    return request<Observation[]>('/observations' + (qs ? '?' + qs : ''));
  },
  create: (o: NewObservation) => request<Observation>('/observations', { method: 'POST', body: JSON.stringify(o) }),
  remove: (id: number) => request<void>(`/observations/${id}`, { method: 'DELETE' }),
  react: (id: number, kind: ReactionKind | null, at?: { lat: number; lon: number }) =>
    request<Observation>(`/observations/${id}/reactions`, {
      method: 'POST',
      body: JSON.stringify({ kind, lat: at?.lat, lon: at?.lon }),
    }),
  uploadPhoto: (id: number, uri: string) => {
    const form = new FormData();
    // React Native's FormData accepts a file descriptor object
    form.append('file', { uri, name: 'photo.jpg', type: 'image/jpeg' } as unknown as Blob);
    return request<Observation>(`/observations/${id}/photo`, { method: 'POST', body: form });
  },
  weather: (lat: number, lon: number) => request<Weather>(`/weather?lat=${lat}&lon=${lon}`),
  alerts: () => request<Alert[]>('/alerts'),
};
