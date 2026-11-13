import { router, useFocusEffect } from 'expo-router';
import * as SMS from 'expo-sms';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Platform, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import MapView, { Marker, Polygon, UrlTile, type Region } from 'react-native-maps';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path } from 'react-native-svg';

import { StatusPill } from '@/components/ui';
import { api } from '@/lib/api';
import { ago, km, leftText } from '@/lib/format';
import { distanceKm, useFix } from '@/lib/location';
import { onIceLeftMs, useSettings } from '@/lib/settings';
import { levelColors, usePalette } from '@/lib/theme';
import type { Alert, Weather, ZoneFeature } from '@/lib/types';

// Vladivostok: Amur and Ussuri bays
const START: Region = { latitude: 43.22, longitude: 132.08, latitudeDelta: 0.5, longitudeDelta: 0.5 };
// EXPO_PUBLIC_MAP_TILES=osm draws OpenStreetMap tiles on top of the system map (no Google key needed on Android).
const OSM = process.env.EXPO_PUBLIC_MAP_TILES === 'osm';

export default function MapScreen() {
  const c = usePalette();
  const insets = useSafeAreaInsets();
  const mapRef = useRef<MapView>(null);
  const { fix, refresh: refreshFix } = useFix();
  const { settings, update } = useSettings();

  const [zones, setZones] = useState<ZoneFeature[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [weather, setWeather] = useState<Weather | null>(null);
  const [picked, setSelId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [banHidden, setBanHidden] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    try {
      const [z, a] = await Promise.all([api.zones(), api.alerts()]);
      setZones(z.features);
      setAlerts(a);
      setError(null);
    } catch {
      setError('Нет связи с сервером. Показаны последние данные.');
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
      const t = setInterval(() => {
        load();
        setNow(Date.now());
      }, 60_000);
      return () => clearInterval(t);
    }, [load]),
  );

  useEffect(() => {
    const p = fix ?? { lat: START.latitude, lon: START.longitude };
    api.weather(p.lat, p.lon).then(setWeather).catch(() => undefined);
  }, [fix]);

  const withDist = useMemo(
    () =>
      zones
        .map((z) => ({ z, d: fix ? distanceKm(fix, z.properties.center) : null }))
        .sort((a, b) => (a.d ?? 0) - (b.d ?? 0)),
    [zones, fix],
  );

  // default selection: nearest zone
  const selId = picked ?? withDist[0]?.z.id ?? null;

  const sel = withDist.find((x) => x.z.id === selId);
  const ban = alerts.find((a) => a.kind === 'ban');
  const iceLeft = onIceLeftMs(settings, now);

  function focusZone(z: ZoneFeature) {
    setSelId(z.id);
    mapRef.current?.animateToRegion(
      { latitude: z.properties.center.lat, longitude: z.properties.center.lon, latitudeDelta: 0.08, longitudeDelta: 0.08 },
      400,
    );
  }

  function onSearch(text: string) {
    setQ(text);
    const s = text.trim().toLowerCase();
    if (!s) return;
    const hit = zones.find((z) => z.properties.name.toLowerCase().startsWith(s));
    if (hit && hit.id !== selId) focusZone(hit);
  }

  async function locate() {
    const f = await refreshFix();
    if (f) mapRef.current?.animateToRegion({ latitude: f.lat, longitude: f.lon, latitudeDelta: 0.1, longitudeDelta: 0.1 }, 400);
  }

  async function smsLate() {
    const contact = settings.onIce.contact;
    if (!contact) return router.push('/profile');
    const where = fix ? `${fix.lat.toFixed(5)}, ${fix.lon.toFixed(5)}` : 'координаты неизвестны';
    if (await SMS.isAvailableAsync()) await SMS.sendSMSAsync([contact], `Я задерживаюсь на льду. Мои координаты: ${where}`);
  }

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <MapView
        ref={mapRef}
        style={StyleSheet.absoluteFill}
        initialRegion={START}
        showsUserLocation
        showsMyLocationButton={false}
        toolbarEnabled={false}
        mapType={OSM && Platform.OS === 'android' ? 'none' : 'standard'}
        mapPadding={{ top: 200, bottom: 230, left: 0, right: 0 }}
      >
        {OSM && <UrlTile urlTemplate="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maximumZ={19} shouldReplaceMapContent />}
        {zones.map((z) => {
          const lc = levelColors(c, z.properties.status.level);
          const selected = z.id === selId;
          return (
            <Polygon
              key={z.id}
              coordinates={z.geometry.coordinates[0].map(([lon, lat]) => ({ latitude: lat, longitude: lon }))}
              fillColor={lc.fill}
              strokeColor={selected ? c.ink : lc.stroke}
              strokeWidth={selected ? 3 : 2}
              lineDashPattern={lc.dashed ? [6, 4] : undefined}
              tappable
              onPress={() => setSelId(z.id)}
            />
          );
        })}
        {zones.map((z) => (
          <Marker
            key={'l-' + z.id}
            coordinate={{ latitude: z.properties.center.lat, longitude: z.properties.center.lon }}
            anchor={{ x: 0.5, y: 0.5 }}
            tracksViewChanges={false}
            onPress={() => setSelId(z.id)}
            accessibilityLabel={`${z.properties.name}: ${z.properties.status.label}`}
          >
            <Text style={[st.zoneLabel, { color: '#0B1B2B' }]}>{z.properties.name}</Text>
          </Marker>
        ))}
      </MapView>

      {/* top overlays */}
      <View style={[st.top, { top: insets.top + 10 }]} pointerEvents="box-none">
        <View style={st.row}>
          <View style={[st.search, { backgroundColor: c.surface }]}>
            <Svg width={20} height={20} viewBox="0 0 24 24" fill="none" stroke={c.muted} strokeWidth={2} strokeLinecap="round">
              <Circle cx={11} cy={11} r={7} />
              <Path d="M20 20l-4-4" />
            </Svg>
            <TextInput
              value={q}
              onChangeText={onSearch}
              placeholder="Участок: Шамора, Седанка…"
              placeholderTextColor={c.muted}
              style={{ flex: 1, color: c.ink, fontSize: 15 }}
              accessibilityLabel="Поиск участка"
              returnKeyType="search"
            />
          </View>
          <Pressable style={[st.fbtn, { backgroundColor: c.surface }]} onPress={locate} accessibilityLabel="Моё местоположение">
            <Svg width={22} height={22} viewBox="0 0 24 24" fill="none" stroke={c.accent} strokeWidth={2} strokeLinecap="round">
              <Circle cx={12} cy={12} r={4} />
              <Path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
            </Svg>
          </Pressable>
        </View>
        {weather && (
          <View style={[st.row, { flexWrap: 'wrap' }]}>
            <Text style={[st.chip, { backgroundColor: c.surface, color: c.ink }]}>{Math.round(weather.temp_c)} °C</Text>
            <Text style={[st.chip, { backgroundColor: c.riskBg, color: c.riskInk }]}>
              Ветер {weather.wind_from} {Math.round(weather.wind_ms)} м/с
            </Text>
            {weather.source === 'fallback' && (
              <Text style={[st.chip, { backgroundColor: c.surface2, color: c.muted }]}>погода: демо</Text>
            )}
          </View>
        )}
        {iceLeft != null && (
          <View style={[st.banner, iceLeft <= 0 ? { backgroundColor: c.danger, borderColor: c.danger } : { backgroundColor: c.surface, borderColor: c.accent }]}>
            <Text style={{ flex: 1, color: iceLeft <= 0 ? '#fff' : c.ink, fontSize: 13 }}>
              {iceLeft <= 0 ? (
                <Text style={{ fontWeight: '800' }}>Время возвращения прошло {leftText(iceLeft)} назад.</Text>
              ) : (
                <>
                  <Text style={{ fontWeight: '800' }}>Вы на льду</Text> · вернуться через {leftText(iceLeft)}
                </>
              )}
            </Text>
            {iceLeft <= 0 && (
              <Pressable onPress={smsLate} style={[st.bannerBtn, { borderColor: '#fff' }]}>
                <Text style={{ color: '#fff', fontWeight: '800', fontSize: 12 }}>SMS контакту</Text>
              </Pressable>
            )}
            <Pressable
              onPress={() => update({ onIce: { ...settings.onIce, active: false } })}
              style={[st.bannerBtn, { borderColor: iceLeft <= 0 ? '#fff' : c.line2 }]}
            >
              <Text style={{ color: iceLeft <= 0 ? '#fff' : c.ink, fontWeight: '800', fontSize: 12 }}>Я на берегу</Text>
            </Pressable>
          </View>
        )}
        {ban && ban.kind === 'ban' && !banHidden && (
          <Pressable
            style={[st.banner, { backgroundColor: c.surface, borderColor: c.danger }]}
            onPress={() => router.push(`/zone/${ban.zone_id}`)}
          >
            <Text style={{ flex: 1, color: c.ink, fontSize: 13 }}>
              <Text style={{ fontWeight: '800' }}>{ban.text}</Text> — {ban.zone_name}. Подробнее
            </Text>
            <Pressable onPress={() => setBanHidden(true)} accessibilityLabel="Скрыть" hitSlop={10}>
              <Text style={{ color: c.muted, fontSize: 18, fontWeight: '700' }}>×</Text>
            </Pressable>
          </Pressable>
        )}
        {error && <Text style={[st.chip, { backgroundColor: c.dangerBg, color: c.dangerInk, alignSelf: 'flex-start' }]}>{error}</Text>}
      </View>

      {/* bottom overlays */}
      <View style={st.bottom} pointerEvents="box-none">
        <View style={[st.row, { justifyContent: 'space-between', alignItems: 'flex-end', paddingHorizontal: 12 }]} pointerEvents="box-none">
          <View style={[st.legend, { backgroundColor: c.surface }]} accessibilityLabel="Легенда">
            {(['danger', 'risk', 'nodata', 'clear'] as const).map((l) => {
              const lc = levelColors(c, l);
              return (
                <View key={l} style={st.legendItem}>
                  <View style={[st.sw, { backgroundColor: lc.fill, borderColor: lc.stroke, borderStyle: lc.dashed ? 'dashed' : 'solid' }]} />
                  <Text style={{ fontSize: 12, fontWeight: '600', color: c.ink }}>
                    {{ danger: 'Опасно', risk: 'Есть риск', nodata: 'Нет данных', clear: 'Тревог нет*' }[l]}
                  </Text>
                </View>
              );
            })}
          </View>
          <View style={[st.row, { gap: 10 }]}>
            <Pressable style={[st.sos, { borderColor: c.surface }]} onPress={() => router.push('/sos')} accessibilityLabel="SOS, экстренная помощь">
              <Text style={{ color: '#fff', fontWeight: '800', fontSize: 15 }}>SOS</Text>
            </Pressable>
            <Pressable
              style={[st.add, { backgroundColor: c.accent }]}
              onPress={() => router.push(selId ? `/add?zone=${selId}` : '/add')}
              accessibilityLabel="Добавить наблюдение"
            >
              <Svg width={26} height={26} viewBox="0 0 24 24" fill="none" stroke={c.onAccent} strokeWidth={2.6} strokeLinecap="round">
                <Path d="M12 5v14M5 12h14" />
              </Svg>
            </Pressable>
          </View>
        </View>
        {sel && (
          <Pressable style={[st.sheet, { backgroundColor: c.surface }]} onPress={() => router.push(`/zone/${sel.z.id}`)} accessibilityRole="button">
            <View style={[st.grab, { backgroundColor: c.line2 }]} />
            <View style={[st.row, { justifyContent: 'space-between' }]}>
              <Text style={{ fontSize: 18, fontWeight: '800', color: c.ink, flexShrink: 1 }}>
                {sel.z.properties.name}
                {sel.d != null ? ` · ${km(sel.d)}` : ''}
              </Text>
              <StatusPill level={sel.z.properties.status.level} />
            </View>
            <Text style={{ fontSize: 14, color: c.muted, lineHeight: 20 }}>
              Свежих наблюдений: {sel.z.properties.status.fresh_count} · последнее {ago(sel.z.properties.status.last_observed_at)}
              {'\n'}
              {sel.z.properties.status.reasons[0] ?? sel.z.properties.status.advice}
            </Text>
            <Text style={{ fontSize: 12, color: c.muted }}>
              *Отсутствие тревог не означает, что лёд безопасен{OSM ? ' · Карта © участники OpenStreetMap' : ''}
            </Text>
          </Pressable>
        )}
      </View>
    </View>
  );
}

const shadow = { shadowColor: '#0B1B2B', shadowOpacity: 0.15, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 4 };

const st = StyleSheet.create({
  top: { position: 'absolute', left: 12, right: 12, gap: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  search: { flex: 1, height: 48, borderRadius: 14, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 14, ...shadow },
  fbtn: { width: 48, height: 48, borderRadius: 14, alignItems: 'center', justifyContent: 'center', ...shadow },
  chip: { borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, fontSize: 13, fontWeight: '700', overflow: 'hidden' },
  banner: { borderWidth: 2, borderRadius: 14, padding: 10, flexDirection: 'row', alignItems: 'center', gap: 8, ...shadow },
  bannerBtn: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 10, paddingVertical: 8 },
  bottom: { position: 'absolute', left: 0, right: 0, bottom: 0, gap: 10 },
  legend: { borderRadius: 14, padding: 10, flexDirection: 'row', flexWrap: 'wrap', width: 210, rowGap: 6, columnGap: 10, ...shadow },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6, width: 90 },
  sw: { width: 14, height: 14, borderRadius: 4, borderWidth: 1.5 },
  sos: { width: 56, height: 56, borderRadius: 28, backgroundColor: '#B3261E', borderWidth: 3, alignItems: 'center', justifyContent: 'center', ...shadow },
  add: { width: 56, height: 56, borderRadius: 18, alignItems: 'center', justifyContent: 'center', ...shadow },
  sheet: { borderTopLeftRadius: 22, borderTopRightRadius: 22, paddingHorizontal: 20, paddingTop: 10, paddingBottom: 14, gap: 6, ...shadow },
  grab: { alignSelf: 'center', width: 40, height: 5, borderRadius: 3 },
  zoneLabel: { fontSize: 12, fontWeight: '800', textShadowColor: '#fff', textShadowRadius: 3, textShadowOffset: { width: 0, height: 0 } },
});
