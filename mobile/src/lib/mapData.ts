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

async function refresh() {
  try {
    const [g, p] = await Promise.all([api.grid(), api.places()]);
    memory = {
      cells: g.cells.map(([id, k, b, lat, lon]) => ({ id, kind: g.kinds[k], bay: g.bays[b], lat, lon })),
      places: p,
    };
    listeners.forEach((l) => l());
    AsyncStorage.setItem(KEY, JSON.stringify(memory)).catch(() => undefined);
  } catch {
    // offline: keep what we have
  }
}

function ensure() {
  if (!loading) {
    loading = (async () => {
      if (!memory) {
        try {
          const raw = await AsyncStorage.getItem(KEY);
          if (raw) {
            memory = JSON.parse(raw);
            listeners.forEach((l) => l());
          }
        } catch {}
      }
      await refresh();
    })();
  }
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
