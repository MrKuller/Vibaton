import { router, useFocusEffect } from 'expo-router';
import * as SMS from 'expo-sms';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import Svg, { Circle, Path } from 'react-native-svg';

import { IceMap, type MapCluster, type MapFocus } from '@/components/IceMap';
import { StatusPill } from '@/components/ui';
import { api } from '@/lib/api';
import { ago, km, leftText } from '@/lib/format';
import { distanceKm, useFix } from '@/lib/location';
import { nearestCell, useMapData } from '@/lib/mapData';
import { onIceLeftMs, useSettings } from '@/lib/settings';
import { levelColors, usePalette } from '@/lib/theme';
import type { Alert, StatusMap, Weather, ZoneDetail } from '@/lib/types';

// Vladivostok: Amur and Ussuri bays
const START = { lat: 43.17, lon: 132.0, zoom: 10 };
// the OpenStreetMap attribution sits at the bottom of the map and must stay visible
const COPYRIGHT_SPACE = 30;

export default function MapScreen() {
  const c = usePalette();
  const insets = useSafeAreaInsets();
  const { fix, refresh: refreshFix } = useFix();
  const { settings, update } = useSettings();
  const { cells, places } = useMapData();

  const [status, setStatus] = useState<StatusMap | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [weather, setWeather] = useState<Weather | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [detail, setDetail] = useState<ZoneDetail | null>(null);
  const [focus, setFocus] = useState<MapFocus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [banHidden, setBanHidden] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    try {
      const [s, a] = await Promise.all([api.status(), api.alerts()]);
      setStatus(s);
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
    const p = fix ?? START;
    api.weather(p.lat, p.lon).then(setWeather).catch(() => undefined);
  }, [fix]);

  // default selection: the cell under the user if they are on the water, else nothing
  const userCell = useMemo(() => (fix && cells.length ? nearestCell(cells, fix) : null), [fix, cells]);
  const selId = picked ?? (userCell && userCell.km < 1.5 ? userCell.cell.id : null);

  useEffect(() => {
    if (!selId) return;
    let alive = true;
    api
      .zone(selId)
      .then((z) => alive && setDetail(z))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [selId, status]);

  const statuses = useMemo(() => status?.cells ?? {}, [status]);
  const ban = alerts.find((a) => a.kind === 'ban');
  const iceLeft = onIceLeftMs(settings, now);
  const clusters = useMemo<MapCluster[]>(
    () =>
      alerts.flatMap((a) => (a.kind === 'cluster' ? [{ lat: a.lat, lon: a.lon, level: a.level, text: a.text }] : [])),
    [alerts],
  );
  const user = useMemo(() => (fix ? { lat: fix.lat, lon: fix.lon } : null), [fix]);
  const sel = detail && detail.id === selId ? detail : null;
  const counts = useMemo(() => {
    const n = { danger: 0, risk: 0, clear: 0 };
    for (const s of Object.values(statuses)) if (s.level in n) n[s.level as keyof typeof n]++;
    return n;
  }, [statuses]);

  function onSearch(text: string) {
    setQ(text);
    const s = text.trim().toLowerCase();
    if (!s) return;
    const hit = places.find((p) => p.name.toLowerCase().startsWith(s));
    if (hit && hit.cell_id !== selId) {
      setPicked(hit.cell_id);
      setFocus({ lat: hit.lat, lon: hit.lon, zoom: 13, nonce: Date.now() });
    }
  }

  async function locate() {
    const f = await refreshFix();
    if (f) setFocus({ lat: f.lat, lon: f.lon, zoom: 13, nonce: Date.now() });
  }

  async function smsLate() {
    const contact = settings.onIce.contact;
    if (!contact) return router.push('/profile');
    const where = fix ? `${fix.lat.toFixed(5)}, ${fix.lon.toFixed(5)}` : 'координаты неизвестны';
    if (await SMS.isAvailableAsync()) await SMS.sendSMSAsync([contact], `Я задерживаюсь на льду. Мои координаты: ${where}`);
  }

  return (
    <View style={{ flex: 1, backgroundColor: c.bg }}>
      <View style={{ flex: 1 }}>
        <IceMap
          style={StyleSheet.absoluteFill}
          cells={cells}
          statuses={statuses}
          places={places}
          selectedId={selId}
          clusters={clusters}
          user={user}
          focus={focus}
          initial={START}
          onSelectCell={setPicked}
        />

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
                placeholder="Место: Шамора, Седанка…"
                placeholderTextColor={c.muted}
                style={{ flex: 1, color: c.ink, fontSize: 15 }}
                accessibilityLabel="Поиск места"
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
            <View
              style={[
                st.banner,
                iceLeft <= 0 ? { backgroundColor: c.danger, borderColor: c.danger } : { backgroundColor: c.surface, borderColor: c.accent },
              ]}
            >
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
          {error && (
            <Text style={[st.chip, { backgroundColor: c.dangerBg, color: c.dangerInk, alignSelf: 'flex-start' }]}>{error}</Text>
          )}
        </View>

        {/* legend and buttons, raised above the attribution line */}
        <View style={[st.mapBottom, { bottom: COPYRIGHT_SPACE }]} pointerEvents="box-none">
          <View style={[st.legend, { backgroundColor: c.surface }]} accessibilityLabel="Легенда">
            {(['danger', 'risk', 'clear', 'nodata'] as const).map((l) => {
              const lc = levelColors(c, l);
              return (
                <View key={l} style={st.legendItem}>
                  <View style={[st.sw, { backgroundColor: lc.fill, borderColor: lc.stroke }]} />
                  <Text style={{ fontSize: 12, fontWeight: '600', color: c.ink }}>
                    {{ danger: 'Опасно', risk: 'Есть риск', clear: 'Тревог нет*', nodata: 'Нет данных' }[l]}
                  </Text>
                </View>
              );
            })}
            {clusters.length > 0 && (
              <View style={[st.legendItem, { width: 190 }]}>
                <View style={[st.sw, { borderRadius: 7, backgroundColor: 'rgba(179,38,30,0.25)', borderColor: '#7A120D', borderStyle: 'dashed' }]} />
                <Text style={{ fontSize: 12, fontWeight: '600', color: c.ink }}>Несколько сигналов рядом</Text>
              </View>
            )}
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
      </View>

      {sel ? (
        <Pressable style={[st.sheet, { backgroundColor: c.surface, borderColor: c.line }]} onPress={() => router.push(`/zone/${sel.id}`)} accessibilityRole="button">
          <View style={[st.row, { justifyContent: 'space-between' }]}>
            <Text style={{ fontSize: 17, fontWeight: '800', color: c.ink, flexShrink: 1 }}>
              {sel.name}
              {fix ? ` · ${km(distanceKm(fix, sel.center))}` : ''}
            </Text>
            <StatusPill level={sel.status.level} />
          </View>
          <Text style={{ fontSize: 14, color: c.muted, lineHeight: 20 }}>
            Свежих наблюдений: {sel.status.fresh_count} · последнее {ago(sel.status.last_observed_at)}
            {'\n'}
            {sel.status.reasons[0] ?? sel.status.advice}
          </Text>
          <Text style={{ fontSize: 12, color: c.muted }}>*Отсутствие тревог не означает, что лёд безопасен</Text>
        </Pressable>
      ) : (
        <View style={[st.sheet, { backgroundColor: c.surface, borderColor: c.line }]}>
          <Text style={{ fontSize: 15, fontWeight: '800', color: c.ink }}>
            Опасно: {counts.danger} · Есть риск: {counts.risk} · Тревог нет: {counts.clear}
          </Text>
          <Text style={{ fontSize: 13, color: c.muted, lineHeight: 19 }}>
            Вся вода разбита на участки: в открытой воде около 0,7 км², у берега около 0,1 км², на реке — полосой по 65 м. Серые — свежих наблюдений нет, обстановка неизвестна.
            Нажмите на участок, чтобы открыть его.
          </Text>
        </View>
      )}
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
  mapBottom: { position: 'absolute', left: 12, right: 12, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-end', gap: 10 },
  legend: { borderRadius: 14, padding: 10, flexDirection: 'row', flexWrap: 'wrap', width: 210, rowGap: 6, columnGap: 10, ...shadow },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6, width: 90 },
  sw: { width: 14, height: 14, borderRadius: 4, borderWidth: 1.5 },
  sos: { width: 56, height: 56, borderRadius: 28, backgroundColor: '#B3261E', borderWidth: 3, alignItems: 'center', justifyContent: 'center', ...shadow },
  add: { width: 56, height: 56, borderRadius: 18, alignItems: 'center', justifyContent: 'center', ...shadow },
  sheet: { borderTopWidth: 1, paddingHorizontal: 20, paddingTop: 12, paddingBottom: 14, gap: 6 },
});
