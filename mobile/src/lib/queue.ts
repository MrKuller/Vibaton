import AsyncStorage from '@react-native-async-storage/async-storage';

import { api, ApiError, isNetworkError } from './api';
import type { NewObservation } from './types';

/** Observations made without network. observed_at keeps the real time of the observation. */
const KEY = 'kl.queue';

interface Queued {
  body: NewObservation;
  photoUri?: string;
}

async function read(): Promise<Queued[]> {
  try {
    return JSON.parse((await AsyncStorage.getItem(KEY)) ?? '[]');
  } catch {
    return [];
  }
}

export async function enqueue(body: NewObservation, photoUri?: string) {
  const q = await read();
  q.push({ body: { ...body, observed_at: body.observed_at ?? new Date().toISOString() }, photoUri });
  await AsyncStorage.setItem(KEY, JSON.stringify(q));
}

export async function queuedCount() {
  return (await read()).length;
}

let flushing = false;
/** Sends what it can. Items the server rejects (e.g. older than 24 h) are dropped. */
export async function flushQueue(): Promise<number> {
  if (flushing) return 0;
  flushing = true;
  let sent = 0;
  try {
    const q = await read();
    const left: Queued[] = [];
    for (const item of q) {
      try {
        const o = await api.create(item.body);
        if (item.photoUri) await api.uploadPhoto(o.id, item.photoUri).catch(() => undefined);
        sent++;
      } catch (e) {
        // keep it for later when offline or logged out; drop what the server rejects (e.g. older than 24 h)
        if (isNetworkError(e) || (e instanceof ApiError && (e.status === 401 || e.status === 429))) left.push(item);
      }
    }
    await AsyncStorage.setItem(KEY, JSON.stringify(left));
  } finally {
    flushing = false;
  }
  return sent;
}
