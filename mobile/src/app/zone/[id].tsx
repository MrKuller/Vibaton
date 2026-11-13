import { router, Stack, useFocusEffect, useLocalSearchParams } from 'expo-router';
import { useCallback, useState } from 'react';
import { ActivityIndicator, Alert as RNAlert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import MapView, { Polygon } from 'react-native-maps';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ObservationCard } from '@/components/ObservationCard';
import { Button, Card, Disclaimer, ErrorBox, StatusPill } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { ago } from '@/lib/format';
import { getFix } from '@/lib/location';
import { useSettings } from '@/lib/settings';
import { levelColors, usePalette } from '@/lib/theme';
import type { Observation, ReactionKind, ZoneDetail } from '@/lib/types';

export default function ZoneScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const c = usePalette();
  const insets = useSafeAreaInsets();
  const { settings, update } = useSettings();
  const [zone, setZone] = useState<ZoneDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setZone(await api.zone(id));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Нет связи с сервером');
    }
  }, [id]);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  const fav = settings.favorites.includes(id);
  const toggleFav = () =>
    update({ favorites: fav ? settings.favorites.filter((f) => f !== id) : [...settings.favorites, id] });

  async function react(o: Observation, kind: ReactionKind) {
    const next = o.my_reaction === kind ? null : kind;
    try {
      const at = next === 'confirm' ? await getFix() : null;
      if (next === 'confirm' && !at) {
        RNAlert.alert('Нужна геолокация', 'Подтвердить можно только рядом с участком.');
        return;
      }
      const upd = await api.react(o.id, next, at ?? undefined);
      setZone((z) => z && { ...z, observations: z.observations.map((x) => (x.id === upd.id ? upd : x)) });
      load();
    } catch (e) {
      RNAlert.alert('Не получилось', e instanceof ApiError ? e.message : 'Нет связи с сервером');
    }
  }

  function remove(o: Observation) {
    RNAlert.alert('Удалить наблюдение?', 'Подтверждения других людей тоже пропадут.', [
      { text: 'Отмена', style: 'cancel' },
      {
        text: 'Удалить',
        style: 'destructive',
        onPress: () => api.remove(o.id).then(load).catch(() => RNAlert.alert('Не получилось удалить')),
      },
    ]);
  }

  if (!zone) {
    return (
      <View style={[s.center, { backgroundColor: c.bg }]}>
        <Stack.Screen options={{ title: 'Участок' }} />
        {error ? <ErrorBox message={error} onRetry={load} /> : <ActivityIndicator />}
      </View>
    );
  }

  const st = zone.status;
  const lc = levelColors(c, st.level);
  const box = {
    danger: { bg: c.dangerBg, fg: c.dangerInk },
    risk: { bg: c.riskBg, fg: c.riskInk },
    clear: { bg: c.accentBg, fg: c.accentInk },
    nodata: { bg: c.surface2, fg: c.ink },
  }[st.level];
  const coords = zone.geometry.coordinates[0].map(([lon, lat]) => ({ latitude: lat, longitude: lon }));

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <Stack.Screen
        options={{
          title: zone.name,
          headerRight: () => (
            <Pressable onPress={toggleFav} accessibilityLabel={fav ? 'Убрать из избранного' : 'В избранное'} hitSlop={10}>
              <Text style={{ fontSize: 24, color: fav ? c.riskEdge : c.muted }}>{fav ? '★' : '☆'}</Text>
            </Pressable>
          ),
        }}
      />
      <ScrollView
        contentContainerStyle={{ padding: 16, gap: 12 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={async () => { setRefreshing(true); await load(); setRefreshing(false); }} />}
      >
        <Text style={{ color: c.muted, fontSize: 13 }}>{zone.bay}</Text>
        <View style={[s.status, { backgroundColor: box.bg }]}>
          <View style={s.row}>
            <StatusPill level={st.level} />
            <Text style={{ color: box.fg, fontSize: 12, fontWeight: '700' }}>
              {st.last_observed_at ? `последнее ${ago(st.last_observed_at)}` : 'нет наблюдений'}
            </Text>
          </View>
          <Text style={{ color: box.fg, fontSize: 14, lineHeight: 20 }}>{st.advice}</Text>
          {st.conflict && (
            <Text style={{ color: box.fg, fontSize: 12, fontWeight: '700' }}>Данные противоречат: учитываем худшее свежее сообщение.</Text>
          )}
        </View>

        <MapView
          style={s.mini}
          initialRegion={{ latitude: zone.center.lat, longitude: zone.center.lon, latitudeDelta: 0.06, longitudeDelta: 0.06 }}
          showsUserLocation
          scrollEnabled={false}
          zoomEnabled={false}
          pitchEnabled={false}
          rotateEnabled={false}
          accessibilityLabel={`Участок ${zone.name} на карте`}
        >
          <Polygon coordinates={coords} fillColor={lc.fill} strokeColor={lc.stroke} strokeWidth={2} lineDashPattern={lc.dashed ? [6, 4] : undefined} />
        </MapView>

        <Card>
          <Text style={{ fontWeight: '800', color: c.ink, fontSize: 14 }}>Почему такой статус</Text>
          {st.reasons.length ? (
            st.reasons.map((r) => (
              <Text key={r} style={{ color: c.ink, fontSize: 13, lineHeight: 19 }}>
                • {r}
              </Text>
            ))
          ) : (
            <Text style={{ color: c.muted, fontSize: 13 }}>Сигналов опасности нет.</Text>
          )}
          <Text style={{ color: c.muted, fontSize: 12, lineHeight: 17 }}>
            Свежими считаются сообщения за {st.fresh_window_h} ч. Погода: {Math.round(zone.weather.temp_c)} °C, ветер{' '}
            {zone.weather.wind_from} {Math.round(zone.weather.wind_ms)} м/с
            {zone.weather.source === 'fallback' ? ' (демо)' : ' (Open-Meteo)'}. ИИ только повышает уровень опасности и может
            ошибаться.
          </Text>
        </Card>

        <Text style={{ fontSize: 16, fontWeight: '800', color: c.ink }}>Наблюдения · {zone.observations.length}</Text>
        {zone.observations.length === 0 && (
          <Card>
            <Text style={{ color: c.muted }}>За двое суток наблюдений нет. Если вы на месте, добавьте первое.</Text>
          </Card>
        )}
        {zone.observations.map((o) => (
          <ObservationCard key={o.id} o={o} onReact={react} onDelete={remove} />
        ))}
      </ScrollView>
      <View style={[s.foot, { backgroundColor: c.surface, borderColor: c.line, paddingBottom: insets.bottom + 12 }]}>
        <Button title="Я здесь — добавить наблюдение" onPress={() => router.push(`/add?zone=${zone.id}`)} />
        <Disclaimer />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 16 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  status: { borderRadius: 14, padding: 14, gap: 6 },
  mini: { height: 160, borderRadius: 16, overflow: 'hidden' },
  foot: { borderTopWidth: 1, paddingHorizontal: 16, paddingTop: 12, gap: 8 },
});
