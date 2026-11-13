import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { ObservationCard } from '@/components/ObservationCard';
import { Card, Disclaimer } from '@/components/ui';
import { api, API_URL } from '@/lib/api';
import { ago, hhmm, leftText } from '@/lib/format';
import { queuedCount } from '@/lib/queue';
import { onIceLeftMs, useSettings } from '@/lib/settings';
import { levelColors, usePalette } from '@/lib/theme';
import type { Observation, ZoneFeature } from '@/lib/types';

export default function ProfileScreen() {
  const c = usePalette();
  const { settings, update } = useSettings();
  const [mine, setMine] = useState<Observation[]>([]);
  const [zones, setZones] = useState<ZoneFeature[]>([]);
  const [queued, setQueued] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useFocusEffect(
    useCallback(() => {
      api.observations({ mine: true, hours: 24 * 30 }).then(setMine).catch(() => undefined);
      api.zones().then((z) => setZones(z.features)).catch(() => undefined);
      queuedCount().then(setQueued);
    }, []),
  );
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);

  const until = settings.onIce.until ? new Date(settings.onIce.until) : null;
  const left = onIceLeftMs(settings, now);

  function setOnIce(active: boolean) {
    const u = until && until.getTime() > Date.now() ? until : new Date(Date.now() + 3 * 3600_000);
    update({ onIce: { ...settings.onIce, active, until: u.toISOString() } });
  }
  function shiftUntil(min: number) {
    const base = until && until.getTime() > Date.now() ? until.getTime() : Date.now();
    const u = new Date(Math.max(Date.now() + 15 * 60_000, base + min * 60_000));
    update({ onIce: { ...settings.onIce, until: u.toISOString() } });
  }

  const confirmed = mine.filter((o) => o.counts.confirm > 0).length;
  const wrong = mine.filter((o) => o.counts.wrong > o.counts.confirm).length;
  const favs = zones.filter((z) => settings.favorites.includes(z.id));

  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={{ padding: 16, gap: 14 }} keyboardShouldPersistTaps="handled">
      <Card style={{ gap: 12 }}>
        <Text style={[s.small, { color: c.muted }]}>Имя в ленте (если не анонимно)</Text>
        <TextInput
          value={settings.name}
          onChangeText={(name) => update({ name: name.slice(0, 40) })}
          placeholder="Как вас подписывать"
          placeholderTextColor={c.muted}
          style={[s.input, { color: c.ink, borderColor: c.line2 }]}
        />
        <View style={{ flexDirection: 'row', gap: 8 }}>
          {[
            [mine.length, 'наблюдений за 30 дней'],
            [confirmed, 'подтверждены другими'],
            [wrong, 'отмечены «неверно»'],
          ].map(([n, l]) => (
            <View key={String(l)} style={[s.stat, { backgroundColor: c.surface2 }]}>
              <Text style={{ fontSize: 22, fontWeight: '800', color: c.ink }}>{n}</Text>
              <Text style={{ fontSize: 11, color: c.muted, fontWeight: '600' }}>{l}</Text>
            </View>
          ))}
        </View>
        {queued > 0 && (
          <Text style={{ color: c.riskInk, fontWeight: '700', fontSize: 13 }}>Ждут отправки без сети: {queued}</Text>
        )}
      </Card>

      <View style={[s.onice, { backgroundColor: c.night }]}>
        <View style={s.row}>
          <View style={{ flex: 1, gap: 2 }}>
            <Text style={{ color: '#fff', fontSize: 16, fontWeight: '800' }}>Режим «Я на льду»</Text>
            <Text style={{ color: c.nightMuted, fontSize: 12, lineHeight: 17 }}>
              Если не отметитесь вовремя, на карте появится тревога и кнопка SMS контакту с вашими координатами.
            </Text>
          </View>
          <Switch value={settings.onIce.active} onValueChange={setOnIce} accessibilityLabel="Режим Я на льду" />
        </View>
        <View style={s.row}>
          <Text style={{ color: c.nightMuted, fontSize: 12, fontWeight: '600' }}>Вернусь до</Text>
          <Pressable style={[s.nbtn, { borderColor: c.nightLine }]} onPress={() => shiftUntil(-30)} accessibilityLabel="Раньше на 30 минут">
            <Text style={s.nbtnText}>−30 мин</Text>
          </Pressable>
          <Text style={{ color: '#fff', fontSize: 20, fontWeight: '800' }}>{until ? hhmm(until) : '—'}</Text>
          <Pressable style={[s.nbtn, { borderColor: c.nightLine }]} onPress={() => shiftUntil(30)} accessibilityLabel="Позже на 30 минут">
            <Text style={s.nbtnText}>+30 мин</Text>
          </Pressable>
        </View>
        <TextInput
          value={settings.onIce.contact}
          onChangeText={(contact) => update({ onIce: { ...settings.onIce, contact } })}
          placeholder="Экстренный контакт: +7 900 000-00-00"
          placeholderTextColor={c.nightMuted}
          keyboardType="phone-pad"
          style={[s.input, { color: '#fff', borderColor: c.nightLine }]}
        />
        {left != null && (
          <Text style={{ color: left <= 0 ? '#FFB4AE' : c.risk, fontWeight: '700', fontSize: 13 }}>
            {left <= 0 ? `Время вышло ${leftText(left)} назад` : `До возвращения ${leftText(left)}`}
          </Text>
        )}
      </View>

      <Text style={[s.h2, { color: c.ink }]}>Избранные участки</Text>
      {favs.length === 0 ? (
        <Card>
          <Text style={{ color: c.muted, fontSize: 13 }}>Отметьте участок звёздочкой на его карточке.</Text>
        </Card>
      ) : (
        <Card style={{ padding: 0, gap: 0 }}>
          {favs.map((z, i) => (
            <Pressable
              key={z.id}
              onPress={() => router.push(`/zone/${z.id}`)}
              style={[s.favRow, i > 0 && { borderTopWidth: 1, borderColor: c.line }]}
            >
              <View style={[s.stripe, { backgroundColor: levelColors(c, z.properties.status.level).stroke }]} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: c.ink, fontWeight: '800' }}>{z.properties.name}</Text>
                <Text style={{ color: c.muted, fontSize: 12 }}>
                  {z.properties.status.label} · {ago(z.properties.status.last_observed_at)}
                </Text>
              </View>
              <Text style={{ color: c.muted, fontSize: 18 }}>›</Text>
            </Pressable>
          ))}
        </Card>
      )}

      <Text style={[s.h2, { color: c.ink }]}>Мои наблюдения</Text>
      {mine.length === 0 ? (
        <Card>
          <Text style={{ color: c.muted, fontSize: 13 }}>Вы ещё ничего не публиковали. Кнопка «+» на карте добавляет наблюдение.</Text>
        </Card>
      ) : (
        mine.slice(0, 5).map((o) => <ObservationCard key={o.id} o={o} showZone onOpenZone={(id) => router.push(`/zone/${id}`)} />)
      )}

      <Text style={[s.h2, { color: c.ink }]}>Настройки</Text>
      <Card style={{ gap: 4 }}>
        <View style={s.row}>
          <Text style={[s.setting, { color: c.ink }]}>Публиковать анонимно</Text>
          <Switch value={settings.anonymous} onValueChange={(anonymous) => update({ anonymous })} />
        </View>
        <View style={s.row}>
          <Text style={[s.setting, { color: c.ink }]}>Загрублять точку в постах без тревог (квадрат 200 м)</Text>
          <Switch value={settings.hidePoint} onValueChange={(hidePoint) => update({ hidePoint })} />
        </View>
        <Text style={{ color: c.muted, fontSize: 11, marginTop: 6 }}>Сервер: {API_URL}</Text>
      </Card>
      <Disclaimer />
    </ScrollView>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  small: { fontSize: 12, fontWeight: '700' },
  input: { borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, minHeight: 46, fontSize: 15 },
  stat: { flex: 1, borderRadius: 14, padding: 10, gap: 2 },
  onice: { borderRadius: 20, padding: 16, gap: 12 },
  nbtn: { borderWidth: 1, borderRadius: 10, paddingHorizontal: 10, minHeight: 40, justifyContent: 'center' },
  nbtnText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  h2: { fontSize: 16, fontWeight: '800' },
  favRow: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
  stripe: { width: 10, height: 40, borderRadius: 5 },
  setting: { flex: 1, fontSize: 14, fontWeight: '600', paddingVertical: 8 },
});
