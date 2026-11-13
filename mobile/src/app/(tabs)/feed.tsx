import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert as RNAlert, FlatList, Text, View } from 'react-native';

import { ObservationCard } from '@/components/ObservationCard';
import { useReportSheet } from '@/components/ReportSheet';
import { Card, Chip, ErrorBox } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { getFix, useFix } from '@/lib/location';
import { usePalette } from '@/lib/theme';
import type { Observation, ReactionKind } from '@/lib/types';

export default function FeedScreen() {
  const c = usePalette();
  const { fix } = useFix();
  const { user } = useAuth();
  const [items, setItems] = useState<Observation[]>([]);
  const [filters, setFilters] = useState({ near: true, hazards: false, fresh: false });
  const [error, setError] = useState<string | null>(null);
  const { open: report, sheet: reportSheet } = useReportSheet((o) =>
    setItems((xs) => xs.map((x) => (x.id === o.id ? { ...x, my_report: true } : x))),
  );
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const near = filters.near && fix;
      setItems(
        await api.observations({
          lat: near ? fix.lat : undefined,
          lon: near ? fix.lon : undefined,
          radius_km: near ? 10 : undefined,
          only_hazards: filters.hazards,
          fresh_only: filters.fresh,
        }),
      );
      setError(null);
    } catch {
      setError('Нет связи с сервером');
    } finally {
      setLoading(false);
    }
  }, [filters, fix]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function react(o: Observation, kind: ReactionKind) {
    if (!user) return router.push('/login');
    const next = o.my_reaction === kind ? null : kind;
    try {
      const at = next === 'confirm' ? await getFix() : null;
      const upd = await api.react(o.id, next, at ?? undefined);
      setItems((xs) => xs.map((x) => (x.id === upd.id ? upd : x)));
    } catch (e) {
      RNAlert.alert('Не получилось', e instanceof ApiError ? e.message : 'Нет связи с сервером');
    }
  }

  const toggle = (k: keyof typeof filters) => setFilters((f) => ({ ...f, [k]: !f[k] }));

  return (
    <FlatList
      style={{ backgroundColor: c.bg }}
      contentContainerStyle={{ padding: 16, gap: 12 }}
      data={items}
      keyExtractor={(o) => String(o.id)}
      refreshing={loading}
      onRefresh={load}
      ListHeaderComponent={
        <View style={{ gap: 12 }}>
          <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
            <Chip label={fix ? 'Рядом, до 10 км' : 'Рядом (нет GPS)'} selected={filters.near} onPress={() => toggle('near')} />
            <Chip label="Только опасности" selected={filters.hazards} onPress={() => toggle('hazards')} />
            <Chip label="Свежее 6 ч" selected={filters.fresh} onPress={() => toggle('fresh')} />
          </View>
          {error && <ErrorBox message={error} onRetry={load} />}
        </View>
      }
      ListEmptyComponent={
        !loading && !error ? (
          <Card>
            <Text style={{ color: c.muted }}>По этим фильтрам наблюдений нет. Снимите часть фильтров.</Text>
          </Card>
        ) : undefined
      }
      renderItem={({ item }) => (
        <ObservationCard o={item} showZone onReact={react} onReport={report} onOpenZone={(id) => router.push(`/zone/${id}`)} />
      )}
      ListFooterComponent={
        <>
          <Text style={{ color: c.muted, fontSize: 11, textAlign: 'center' }}>
            Наблюдения старше 24 ч не учитываются в статусе участков.
          </Text>
          {reportSheet}
        </>
      }
    />
  );
}
