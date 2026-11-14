import * as ImagePicker from 'expo-image-picker';
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { Alert as RNAlert, Image, KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { Button, Disclaimer } from '@/components/ui';
import { api, ApiError, isNetworkError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { km } from '@/lib/format';
import { useFix } from '@/lib/location';
import { nearestCell, placesByDistance, useMapData } from '@/lib/mapData';
import { enqueue } from '@/lib/queue';
import { useSettings } from '@/lib/settings';
import { usePalette } from '@/lib/theme';
import type { NewObservation, ObsType } from '@/lib/types';

const TYPES: { id: ObsType; label: string; sev: 'danger' | 'risk' | 'clear' }[] = [
  { id: 'crack', label: 'Трещина', sev: 'risk' },
  { id: 'hole', label: 'Промоина', sev: 'danger' },
  { id: 'water', label: 'Вода на льду', sev: 'risk' },
  { id: 'thin', label: 'Тонкий лёд', sev: 'danger' },
  { id: 'floe', label: 'Отрыв льдины', sev: 'danger' },
  { id: 'clear', label: 'Без тревог', sev: 'clear' },
];
const METHODS = ['Лунка', 'Бур', 'На глаз'];
const ICE = ['Прозрачный', 'Белый слоистый', 'Снег сверху', 'Вода сверху'];

export default function AddScreen() {
  const params = useLocalSearchParams<{ zone?: string }>();
  const c = usePalette();
  const insets = useSafeAreaInsets();
  const { settings } = useSettings();
  const { user, ready: authReady } = useAuth();
  const { fix, state: fixState, refresh } = useFix();

  const { cells, places } = useMapData();
  // undefined = use GPS; a cell id (from the map) or a place id
  const [pickedZone, setZoneId] = useState<string | undefined>(params.zone);
  const [type, setType] = useState<ObsType | null>(null);
  const [thick, setThick] = useState('');
  const [method, setMethod] = useState('Лунка');
  const [ice, setIce] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [photo, setPhoto] = useState<string | null>(null);
  const [anon, setAnon] = useState(settings.anonymous);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const sorted = useMemo(() => placesByDistance(places, fix).slice(0, 8), [places, fix]);
  // on the water (within 1.5 km of a cell) the server finds the cell by GPS
  const onWater = useMemo(() => {
    if (!fix || !cells.length) return false;
    const n = nearestCell(cells, fix);
    return !!n && n.km <= 1.5;
  }, [fix, cells]);
  const zoneId = pickedZone;
  const pickedFromMap = !!zoneId && !places.some((p) => p.id === zoneId);

  function step(d: number) {
    const v = thick === '' ? 18 : Number(thick) || 0;
    setThick(String(Math.max(0, Math.min(150, v + d))));
  }

  async function takePhoto() {
    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) return setErr('Нет доступа к камере. Разрешите его в настройках телефона.');
    const r = await ImagePicker.launchCameraAsync({ quality: 0.6, exif: false, mediaTypes: ['images'] });
    if (!r.canceled && r.assets[0]) setPhoto(r.assets[0].uri);
  }

  function validate(): string | null {
    if (!type) return 'Выберите, что вы видите.';
    if (!zoneId && !onWater) return fix ? 'Вы далеко от льда заливов. Выберите место из списка.' : 'Выберите место: геолокация недоступна.';
    if (thick !== '') {
      if (!/^\d{1,3}$/.test(thick)) return 'Толщина — целое число сантиметров.';
      const n = Number(thick);
      if (n > 150) return 'Толщина должна быть от 0 до 150 см. Проверьте, нет ли опечатки.';
      if (type === 'clear' && n < 10) return 'При толщине меньше 10 см выберите «Тонкий лёд».';
    }
    return null;
  }

  async function publish() {
    const v = validate();
    if (v) return setErr(v);
    setErr('');
    setBusy(true);
    const body: NewObservation = {
      type: type!,
      zone_id: zoneId,
      thickness_cm: thick === '' ? null : Number(thick),
      method: thick === '' ? null : method,
      ice_type: ice,
      text: text.trim(),
      lat: fix?.lat,
      lon: fix?.lon,
      gps_accuracy_m: fix?.accuracy ?? null,
      mocked_location: fix?.mocked ?? false,
      anonymous: anon,
      hide_point: settings.hidePoint,
      observed_at: new Date().toISOString(),
    };
    try {
      const o = await api.create(body);
      if (photo) {
        try {
          const result = await api.uploadPhoto(o.id, photo);
        } catch (e) {

          RNAlert.alert(
            'Фото не принято',
            (e instanceof ApiError ? e.message : String(e)) +
              ' Наблюдение опубликовано без фото.',
          );
        }
      }
      if (o.moderation_status === 'pending') {
        RNAlert.alert('Отправлено на проверку', o.moderation_note ?? 'Модератор посмотрит текст в ближайшее время.');
      }
      router.replace(`/zone/${o.zone_id}`);
    } catch (e) {
      if (isNetworkError(e)) {
        await enqueue(body, photo ?? undefined);
        setBusy(false);
        RNAlert.alert('Сохранено без сети', 'Отправим наблюдение, когда появится связь. Время наблюдения сохранено.');
        router.back();
        return;
      }
      setErr(e instanceof ApiError ? e.message : 'Не получилось опубликовать');
    }
    setBusy(false);
  }

  const sevStyle = (sev: string, on: boolean) =>
    !on
      ? { borderColor: c.line2, backgroundColor: c.surface }
      : sev === 'danger'
        ? { borderColor: c.danger, backgroundColor: c.dangerBg, borderWidth: 2 }
        : sev === 'risk'
          ? { borderColor: c.riskEdge, backgroundColor: c.riskBg, borderWidth: 2 }
          : { borderColor: c.accent, backgroundColor: c.accentBg, borderWidth: 2 };

  if (authReady && !user) {
    return (
      <View style={{ flex: 1, backgroundColor: c.bg, padding: 24, justifyContent: 'center', gap: 14 }}>
        <Text style={{ color: c.ink, fontSize: 20, fontWeight: '800' }}>Войдите, чтобы публиковать</Text>
        <Text style={{ color: c.muted, fontSize: 14, lineHeight: 20 }}>
          Наблюдения публикуются только из аккаунта: так меньше фейков. В ленте можно остаться анонимным.
        </Text>
        <Button title="Войти или зарегистрироваться" onPress={() => router.push('/login')} />
      </View>
    );
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <ScrollView contentContainerStyle={{ padding: 16, gap: 16 }} keyboardShouldPersistTaps="handled">
        <Pressable onPress={refresh} style={[s.gps, { backgroundColor: fix ? c.okBg : c.surface2 }]}>
          <Text style={{ color: fix ? c.okInk : c.ink, fontSize: 13, lineHeight: 18 }}>
            {fixState === 'loading'
              ? 'Определяем местоположение…'
              : fix
                ? `GPS ±${Math.round(fix.accuracy ?? 0)} м · ${fix.lat.toFixed(4)}, ${fix.lon.toFixed(4)}${fix.mocked ? ' · подменённая геолокация' : ''}`
                : 'Геолокация недоступна: наблюдение будет отмечено как сделанное не на месте. Нажмите, чтобы повторить.'}
          </Text>
        </Pressable>

        <View style={{ gap: 8 }}>
          <Text style={[s.label, { color: c.ink }]}>Где</Text>
          <View style={s.wrap}>
            {(onWater || pickedFromMap) && (
              <Pressable
                onPress={() => setZoneId(pickedFromMap ? zoneId : undefined)}
                style={[s.pillBtn, (!zoneId || pickedFromMap) ? { borderColor: c.accent, backgroundColor: c.accentBg, borderWidth: 2 } : { borderColor: c.line2, backgroundColor: c.surface }]}
                accessibilityState={{ selected: !zoneId || pickedFromMap }}
              >
                <Text style={{ color: (!zoneId || pickedFromMap) ? c.accentInk : c.ink, fontWeight: '700', fontSize: 13 }}>
                  {pickedFromMap ? 'Участок, выбранный на карте' : 'Здесь, по GPS'}
                </Text>
              </Pressable>
            )}
            {sorted.map(({ p, d }) => (
              <Pressable
                key={p.id}
                onPress={() => setZoneId(p.id)}
                style={[s.pillBtn, zoneId === p.id ? { borderColor: c.accent, backgroundColor: c.accentBg, borderWidth: 2 } : { borderColor: c.line2, backgroundColor: c.surface }]}
                accessibilityState={{ selected: zoneId === p.id }}
              >
                <Text style={{ color: zoneId === p.id ? c.accentInk : c.ink, fontWeight: '700', fontSize: 13 }}>
                  {p.name}
                  {d != null ? ` · ${km(d)}` : ''}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={{ gap: 8 }}>
          <Text style={[s.label, { color: c.ink }]}>Что вы видите?</Text>
          <View style={s.grid}>
            {TYPES.map((t) => (
              <Pressable
                key={t.id}
                onPress={() => { setType(t.id); setErr(''); }}
                style={[s.type, sevStyle(t.sev, type === t.id)]}
                accessibilityRole="radio"
                accessibilityState={{ checked: type === t.id }}
              >
                <Text style={{ color: c.ink, fontWeight: type === t.id ? '800' : '700', fontSize: 13, textAlign: 'center' }}>{t.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={{ gap: 8 }}>
          <Text style={[s.label, { color: c.ink }]}>
            Толщина льда <Text style={{ color: c.muted, fontWeight: '600' }}>(необязательно)</Text>
          </Text>
          <View style={[s.wrap, { flexWrap: 'nowrap' }]}>
            <Pressable onPress={() => step(-1)} style={[s.step, { borderColor: c.line2, backgroundColor: c.surface }]} accessibilityLabel="Тоньше на 1 см">
              <Text style={[s.stepText, { color: c.ink }]}>−</Text>
            </Pressable>
            <View style={[s.thick, { borderColor: c.line2, backgroundColor: c.surface }]}>
              <TextInput
                value={thick}
                onChangeText={(v) => setThick(v.replace(/[^\d]/g, '').slice(0, 3))}
                keyboardType="number-pad"
                placeholder="—"
                placeholderTextColor={c.muted}
                style={{ fontSize: 22, fontWeight: '800', color: c.ink, minWidth: 48, textAlign: 'right' }}
                accessibilityLabel="Толщина в сантиметрах"
              />
              <Text style={{ color: c.muted, fontSize: 15 }}> см</Text>
            </View>
            <Pressable onPress={() => step(1)} style={[s.step, { borderColor: c.line2, backgroundColor: c.surface }]} accessibilityLabel="Толще на 1 см">
              <Text style={[s.stepText, { color: c.ink }]}>+</Text>
            </Pressable>
          </View>
          <View style={[s.seg, { backgroundColor: c.surface2 }]}>
            {METHODS.map((m) => (
              <Pressable key={m} onPress={() => setMethod(m)} style={[s.segBtn, method === m && { backgroundColor: c.surface }]} accessibilityState={{ selected: method === m }}>
                <Text style={{ color: method === m ? c.ink : c.muted, fontWeight: method === m ? '800' : '600', fontSize: 13 }}>{m}</Text>
              </Pressable>
            ))}
          </View>
          <View style={s.wrap}>
            {ICE.map((i) => (
              <Pressable
                key={i}
                onPress={() => setIce(ice === i ? null : i)}
                style={[s.pillBtn, ice === i ? { borderColor: c.accent, backgroundColor: c.accentBg, borderWidth: 2 } : { borderColor: c.line2, backgroundColor: c.surface }]}
              >
                <Text style={{ color: ice === i ? c.accentInk : c.ink, fontSize: 12, fontWeight: '700' }}>{i}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={{ gap: 8 }}>
          <Text style={[s.label, { color: c.ink }]}>Комментарий</Text>
          <TextInput
            value={text}
            onChangeText={setText}
            maxLength={280}
            multiline
            placeholder="Где именно, как обойти"
            placeholderTextColor={c.muted}
            style={[s.input, { color: c.ink, borderColor: c.line2, backgroundColor: c.surface }]}
          />
        </View>

        <Pressable onPress={takePhoto} style={[s.photo, { borderColor: c.line2, backgroundColor: c.surface }]} accessibilityRole="button">
          {photo ? (
            <Image source={{ uri: photo }} style={{ width: '100%', height: 180, borderRadius: 12 }} accessibilityLabel="Снятое фото" />
          ) : (
            <Text style={{ color: c.ink, fontWeight: '700' }}>Снять фото</Text>
          )}
        </Pressable>
        <Text style={{ color: c.muted, fontSize: 12, marginTop: -10, lineHeight: 17 }}>
          Фото только с камеры. На сервере лица и номера машин размываются, а данные о телефоне и GPS из файла удаляются.
        </Text>
        {!!err && <Text style={{ color: c.danger, fontWeight: '700' }} accessibilityLiveRegion="polite">{err}</Text>}
      </ScrollView>

      <View style={[s.foot, { backgroundColor: c.surface, borderColor: c.line, paddingBottom: insets.bottom + 12 }]}>
        <View style={s.switchRow}>
          <Text style={{ color: c.ink, fontWeight: '600', fontSize: 14 }}>Публиковать анонимно</Text>
          <Switch value={anon} onValueChange={setAnon} />
        </View>
        <Button title={type ? 'Опубликовать' : 'Выберите, что вы видите'} disabled={!type} loading={busy} onPress={publish} />
        <Disclaimer>Нет сети? Сохраним и отправим, когда появится связь.</Disclaimer>
      </View>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  gps: { borderRadius: 14, padding: 12 },
  label: { fontSize: 14, fontWeight: '800' },
  wrap: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, alignItems: 'center' },
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  type: { width: '31.5%', minHeight: 64, borderRadius: 14, borderWidth: 1, alignItems: 'center', justifyContent: 'center', padding: 6 },
  pillBtn: { minHeight: 40, paddingHorizontal: 12, borderRadius: 999, borderWidth: 1, justifyContent: 'center' },
  step: { width: 56, height: 56, borderRadius: 14, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  stepText: { fontSize: 26, fontWeight: '700' },
  thick: { flex: 1, height: 56, borderRadius: 14, borderWidth: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  seg: { flexDirection: 'row', borderRadius: 12, padding: 4, gap: 4 },
  segBtn: { flex: 1, height: 42, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  input: { minHeight: 80, borderWidth: 1, borderRadius: 12, padding: 12, fontSize: 15, textAlignVertical: 'top' },
  photo: { minHeight: 76, borderWidth: 2, borderStyle: 'dashed', borderRadius: 14, alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  foot: { borderTopWidth: 1, paddingHorizontal: 16, paddingTop: 12, gap: 10 },
  switchRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
});
