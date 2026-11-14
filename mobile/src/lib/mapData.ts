import AsyncStorage from '@react-native-async-storage/async-storage';
import { useEffect, useState } from 'react';

import { api } from './api';
import { distanceKm } from './location';
import type { GridCell, Place } from './types';

/**
 * The water grid and named places change only with a new server release: download them once,
 * keep them on the phone (works offline), refresh in the background.
 */
const KEY = 'kl.mapData.v2'; // v2: H3 cells
let memory: { cells: GridCell[]; places: Place[] } | null = null;
let loading: Promise<void> | null = null;
const listeners = new Set<() => void>();


let retryTimer: ReturnType<typeof setTimeout> | null = null;
let retryDelay = 5000;
const MAX_RETRY_DELAY = 60000;

function notify() {
  listeners.forEach((listener) => listener());
}

function scheduleRetry() {
  if (retryTimer) return;

  retryTimer = setTimeout(() => {
    retryTimer = null;
    void ensure();
  }, retryDelay);

  retryDelay = Math.min(retryDelay * 2, MAX_RETRY_DELAY);
}

async function refresh(): Promise<boolean> {
  try {
    const [g, p] = await Promise.all([api.grid(), api.places()]);

    if (
      !Array.isArray(g.cells) ||
      g.cells.length === 0 ||
      !Array.isArray(g.kinds) ||
      !Array.isArray(g.bays) ||
      !Array.isArray(p)
    ) {
      throw new Error('Некорректный ответ API карты');
    }

    const cells: GridCell[] = g.cells.map(([id, k, b, lat, lon]) => {
      const kind = g.kinds[k];
      const bay = g.bays[b];

      if (
        typeof id !== 'string' ||
        typeof kind !== 'string' ||
        typeof bay !== 'string'
      ) {
        throw new Error('Некорректная H3-ячейка');
      }

      return { id, kind, bay, lat, lon };
    });

    memory = { cells, places: p };
    notify();

    void AsyncStorage.setItem(KEY, JSON.stringify(memory));

    retryDelay = 5000;
    if (retryTimer) clearTimeout(retryTimer);
    retryTimer = null;

    return true;
  } catch (error) {
    console.warn('[MapData] Не удалось обновить карту:', error);
    return false;
  }
}

function ensure(): Promise<void> {
  if (loading) return loading;

  loading = (async () => {
    if (!memory) {
      try {
        const raw = await AsyncStorage.getItem(KEY);

        if (raw) {
          const cached = JSON.parse(raw);

          if (
            Array.isArray(cached.cells) &&
            Array.isArray(cached.places)
          ) {
            memory = cached;
            notify();
          }
        }
      } catch (error) {
        console.warn('[MapData] Ошибка чтения кэша:', error);
      }
    }

    const success = await refresh();

    if (!success) {
      scheduleRetry();
    }
  })().finally(() => {
    loading = null;
  });

  return loading;
}

export function useMapData() {
  const [data, setData] = useState(memory);
  useEffect(() => {
    const l = () => setData(memory);
    listeners.add(l);
    ensure().then(l);
    return () => {
      listeners.delete(l);
    };
  }, []);
  return { cells: data?.cells ?? [], places: data?.places ?? [] };
}

export function placesByDistance(places: Place[], from: { lat: number; lon: number } | null) {
  return places
    .map((p) => ({ p, d: from ? distanceKm(from, p) : null }))
    .sort((a, b) => (a.d ?? 0) - (b.d ?? 0) || a.p.name.localeCompare(b.p.name));
}

/** The nearest cell centre to a point (cells: 0.015–0.74 km² hexagons). */
export function nearestCell(cells: GridCell[], at: { lat: number; lon: number }) {
  let best: GridCell | null = null;
  let bestD = Infinity;
  for (const c of cells) {
    const d = distanceKm(at, c);
    if (d < bestD) {
      best = c;
      bestD = d;
    }
  }
  return best ? { cell: best, km: bestD } : null;
}
