import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Card, ErrorBox } from '@/components/ui';
import { api } from '@/lib/api';
import { useFix } from '@/lib/location';
import { usePalette } from '@/lib/theme';
import type { Alert, Weather } from '@/lib/types';

const DEFAULT = { lat: 43.22, lon: 131.95 };

export default function WeatherScreen() {
  const c = usePalette();
  const { fix } = useFix();
  const [w, setW] = useState<Weather | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    const p = fix ?? DEFAULT;
    try {
      const [ww, aa] = await Promise.all([api.weather(p.lat, p.lon), api.alerts()]);
      setW(ww);
      setAlerts(aa);
      setError(null);
    } catch {
      setError('Нет связи с сервером');
    } finally {
      setLoading(false);
    }
  }, [fix]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const maxAbs = Math.max(5, ...(w?.days ?? []).map((d) => Math.abs(d.t_max ?? 0)));

  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={{ padding: 16, gap: 12 }} refreshControl={<RefreshControl refreshing={loading} onRefresh={load} />}>
      {error && <ErrorBox message={error} onRetry={load} />}
      {w && (
        <>
          <View style={[s.hero, { backgroundColor: c.night }]}>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[s.k, { color: c.nightMuted }]}>Воздух</Text>
              <Text style={s.v}>{Math.round(w.temp_c)} °C</Text>
            </View>
            <View style={{ flex: 1, gap: 2 }}>
              <Text style={[s.k, { color: c.nightMuted }]}>Ветер</Text>
              <Text style={s.v}>{Math.round(w.wind_ms)} м/с</Text>
              <Text style={{ color: c.risk, fontWeight: '700', fontSize: 12 }}>
                {w.wind_from}
                {w.wind_gust_ms ? `, порывы до ${Math.round(w.wind_gust_ms)}` : ''}
              </Text>
            </View>
          </View>
          <Card>
            <Text style={{ fontWeight: '800', color: c.ink }}>Максимальная температура по дням</Text>
            <View style={s.bars}>
              {w.days.map((d) => {
                const v = d.t_max ?? 0;
                const warm = v > -5;
                return (
                  <View key={d.date} style={s.barCol}>
                    <Text style={{ fontSize: 11, fontWeight: '700', color: warm ? c.riskInk : c.ink }}>
                      {v > 0 ? '+' : ''}
                      {Math.round(v)}°
                    </Text>
                    <View style={{ width: '100%', height: Math.max(6, (Math.abs(v) / maxAbs) * 80), borderRadius: 6, backgroundColor: warm ? c.risk : c.clearEdge }} />
                    <Text style={{ fontSize: 10, color: c.muted }}>{d.date.slice(5).replace('-', '.')}</Text>
                  </View>
                );
              })}
            </View>
          </Card>
          <Text style={{ color: c.muted, fontSize: 11 }}>
            {w.source === 'fallback'
              ? 'Open-Meteo сейчас недоступен: показаны демо-значения.'
              : 'Источник: Open-Meteo, обновляется раз в 30 минут.'}
          </Text>
        </>
      )}

      <Text style={{ fontSize: 16, fontWeight: '800', color: c.ink, marginTop: 4 }}>Предупреждения</Text>
      {alerts.length === 0 && !error && (
        <Card>
          <Text style={{ color: c.muted }}>Предупреждений нет. Это не значит, что лёд безопасен.</Text>
        </Card>
      )}
      {alerts.map((a, i) => (
        <Card key={i} style={{ borderColor: a.critical ? c.danger : c.risk, borderWidth: 2 }}>
          {a.kind === 'ban' || a.kind === 'cluster' ? (
            <>
              <Text style={{ fontWeight: '800', color: c.ink }}>{a.zone_name}</Text>
              <Text style={{ color: c.ink }}>{a.text}</Text>
              <Text style={{ color: c.accent, fontWeight: '700' }} onPress={() => router.push(`/zone/${a.zone_id}`)}>
                Открыть участок
              </Text>
            </>
          ) : (
            <>
              <Text style={{ fontWeight: '800', color: c.ink }}>ИИ-предупреждение · {a.bay}</Text>
              <Text style={{ color: c.ink, lineHeight: 20 }}>{a.text}</Text>
              <Text style={{ color: c.muted, fontSize: 12, lineHeight: 17 }}>
                Основание: {a.facts.join('; ')}. {a.disclaimer}
              </Text>
            </>
          )}
        </Card>
      ))}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  hero: { borderRadius: 20, padding: 16, flexDirection: 'row', gap: 12 },
  k: { fontSize: 12, fontWeight: '600' },
  v: { color: '#fff', fontSize: 34, fontWeight: '800' },
  bars: { flexDirection: 'row', gap: 8, alignItems: 'flex-end', minHeight: 120 },
  barCol: { flex: 1, alignItems: 'center', justifyContent: 'flex-end', gap: 4 },
});
