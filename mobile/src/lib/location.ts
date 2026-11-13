import * as Location from 'expo-location';
import { useCallback, useEffect, useState } from 'react';

export interface Fix {
  lat: number;
  lon: number;
  accuracy: number | null;
  mocked: boolean;
}

export async function getFix(): Promise<Fix | null> {
  const perm = await Location.requestForegroundPermissionsAsync();
  if (perm.status !== 'granted') return null;
  try {
    const p = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.High });
    return { lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy, mocked: !!p.mocked };
  } catch {
    const last = await Location.getLastKnownPositionAsync();
    return last
      ? { lat: last.coords.latitude, lon: last.coords.longitude, accuracy: last.coords.accuracy, mocked: !!last.mocked }
      : null;
  }
}

export function useFix() {
  const [fix, setFix] = useState<Fix | null>(null);
  const [state, setState] = useState<'loading' | 'ok' | 'denied'>('loading');
  const refresh = useCallback(async () => {
    setState('loading');
    const f = await getFix();
    setFix(f);
    setState(f ? 'ok' : 'denied');
    return f;
  }, []);
  useEffect(() => {
    let alive = true;
    getFix().then((f) => {
      if (!alive) return;
      setFix(f);
      setState(f ? 'ok' : 'denied');
    });
    return () => {
      alive = false;
    };
  }, []);
  return { fix, state, refresh };
}

export function distanceKm(a: { lat: number; lon: number }, b: { lat: number; lon: number }) {
  const R = 6371;
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((a.lat * Math.PI) / 180) * Math.cos((b.lat * Math.PI) / 180) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(s));
}
