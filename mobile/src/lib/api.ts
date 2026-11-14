import type {
  Alert,
  AuthResult,
  Cluster,
  CompactGrid,
  Place,
  StatusMap,
  NewObservation,
  Observation,
  QueueItem,
  ReactionKind,
  ReportReason,
  Weather,
  ZoneDetail,
  User,
} from './types';
import { File } from 'expo-file-system';

// On a phone, localhost is the phone itself: set EXPO_PUBLIC_API_URL=http://<your-computer-ip>:8000
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000').replace(/\/$/, '');

// Set by AuthProvider (src/lib/auth.tsx); the token itself lives in SecureStore.
let authToken: string | null = null;
export function setAuthToken(token: string | null) {
  authToken = token;
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
  if (authToken) headers.set('Authorization', `Bearer ${authToken}`);
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
  register: (b: {
    email: string;
    password: string;
    display_name: string;
    website: string;
  }) => request<AuthResult>('/auth/register', { method: 'POST', body: JSON.stringify(b) }),
  login: (email: string, password: string) =>
    request<AuthResult>('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<User>('/auth/me'),
  clusters: () => request<Cluster[]>('/clusters'),
  grid: () => request<CompactGrid>('/grid'),
  places: () => request<Place[]>('/places'),
  status: () => request<StatusMap>('/status'),
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
    console.log('[PHOTO] URI:', uri);

    try {
      const file = new File(uri);
      const form = new FormData();
      form.append('file', file);

      return request<Observation>(
        `/observations/${id}/photo`,
        {
          method: 'POST',
          body: form,
        },
      );
    }
  },
  report: (id: number, reason: ReportReason, comment = '') =>
    request<{ ok: boolean; message: string }>(`/observations/${id}/reports`, {
      method: 'POST',
      body: JSON.stringify({ reason, comment }),
    }),
  moderationQueue: () => request<QueueItem[]>('/moderation/queue'),
  moderate: (id: number, action: 'approve' | 'hide' | 'delete', note = '', ban_days?: number) =>
    request<{ ok: boolean }>(`/moderation/observations/${id}`, {
      method: 'POST',
      body: JSON.stringify({ action, note, ban_days }),
    }),
  weather: (lat: number, lon: number) => request<Weather>(`/weather?lat=${lat}&lon=${lon}`),
  alerts: () => request<Alert[]>('/alerts'),
};
