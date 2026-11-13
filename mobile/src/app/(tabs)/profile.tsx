import { router, useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { ObservationCard } from '@/components/ObservationCard';
import { Button, Card, Chip, Disclaimer } from '@/components/ui';
import { api, API_URL } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { ago, hhmm, leftText } from '@/lib/format';
import { queuedCount } from '@/lib/queue';
import { onIceLeftMs, useSettings, type ThemeChoice } from '@/lib/settings';
import { levelColors, usePalette } from '@/lib/theme';
import type { Observation, ZoneDetail } from '@/lib/types';

export default function ProfileScreen() {
  const c = usePalette();
  const { settings, update } = useSettings();
  const { user, logout } = useAuth();
  const [mine, setMine] = useState<Observation[]>([]);
  const [favs, setFavs] = useState<ZoneDetail[]>([]);
  const [queued, setQueued] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useFocusEffect(
    useCallback(() => {
      if (user) api.observations({ mine: true, hours: 24 * 30 }).then(setMine).catch(() => undefined);
      else setMine([]);
      Promise.all(settings.favorites.slice(0, 10).map((id) => api.zone(id).catch(() => null)))
        .then((xs) => setFavs(xs.filter((x): x is ZoneDetail => !!x)))
        .catch(() => undefined);
      queuedCount().then(setQueued);
    }, [user, settings.favorites]),
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

  return (
    <ScrollView style={{ backgroundColor: c.bg }} contentContainerStyle={{ padding: 16, gap: 14 }} keyboardShouldPersistTaps="handled">
      {!user ? (
        <Card style={{ gap: 10 }}>
          <Text style={{ color: c.ink, fontSize: 16, fontWeight: '800' }}>Вы не вошли</Text>
          <Text style={{ color: c.muted, fontSize: 13, lineHeight: 19 }}>
            Карта и лента доступны без аккаунта. Чтобы публиковать наблюдения и подтверждать чужие, войдите.
          </Text>
          <Button title="Войти или зарегистрироваться" onPress={() => router.push('/login')} />
        </Card>
      ) : (
      <Card style={{ gap: 12 }}>
        <View style={s.row}>
          <View style={[s.avatar, { backgroundColor: c.ink }]}>
            <Text style={{ color: c.bg, fontWeight: '800', fontSize: 18 }}>{user.display_name.slice(0, 2).toUpperCase()}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={{ color: c.ink, fontSize: 18, fontWeight: '800' }}>{user.display_name}</Text>
            <Text style={{ color: c.muted, fontSize: 13 }}>{user.email}</Text>
          </View>
          <Pressable onPress={logout} style={[s.nbtn, { borderColor: c.line2 }]} accessibilityRole="button">
            <Text style={{ color: c.ink, fontWeight: '700', fontSize: 13 }}>Выйти</Text>
          </Pressable>
        </View>
        {user.banned_until && (
          <Text style={{ color: c.dangerInk, backgroundColor: c.dangerBg, padding: 10, borderRadius: 10, fontWeight: '700', overflow: 'hidden' }}>
            Публикации заблокированы до {new Date(user.banned_until).toLocaleString('ru-RU')} за нарушение правил. Смотреть
            карту можно.
          </Text>
        )}
        {(user.role === 'moderator' || user.role === 'admin') && (
          <Button title="Модерация: очередь жалоб" variant="ghost" onPress={() => router.push('/moderation')} />
        )}
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
      )}

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
              <View style={[s.stripe, { backgroundColor: levelColors(c, z.status.level).stroke }]} />
              <View style={{ flex: 1 }}>
                <Text style={{ color: c.ink, fontWeight: '800' }}>{z.name}</Text>
                <Text style={{ color: c.muted, fontSize: 12 }}>
                  {z.status.label} · {ago(z.status.last_observed_at)}
                </Text>
              </View>
              <Text style={{ color: c.muted, fontSize: 18 }}>›</Text>
            </Pressable>
          ))}
        </Card>
      )}

      {user && <Text style={[s.h2, { color: c.ink }]}>Мои наблюдения</Text>}
      {!user ? null : mine.length === 0 ? (
        <Card>
          <Text style={{ color: c.muted, fontSize: 13 }}>Вы ещё ничего не публиковали. Кнопка «+» на карте добавляет наблюдение.</Text>
        </Card>
      ) : (
        mine.slice(0, 5).map((o) => <ObservationCard key={o.id} o={o} showZone onOpenZone={(id) => router.push(`/zone/${id}`)} />)
      )}

      <Text style={[s.h2, { color: c.ink }]}>Настройки</Text>
      <Card style={{ gap: 4 }}>
        <Text style={[s.setting, { color: c.ink, paddingBottom: 0 }]}>Тема</Text>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, paddingBottom: 8 }}>
          {(
            [
              ['system', 'Как в системе'],
              ['light', 'Светлая'],
              ['dark', 'Тёмная'],
            ] as [ThemeChoice, string][]
          ).map(([k, label]) => (
            <Chip key={k} label={label} selected={settings.theme === k} onPress={() => update({ theme: k })} />
          ))}
        </View>
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
  avatar: { width: 52, height: 52, borderRadius: 26, alignItems: 'center', justifyContent: 'center' },
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
