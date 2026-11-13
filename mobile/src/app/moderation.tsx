import { router, useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { Alert as RNAlert, FlatList, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { ObservationCard } from '@/components/ObservationCard';
import { Card, ErrorBox } from '@/components/ui';
import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { usePalette } from '@/lib/theme';
import type { QueueItem } from '@/lib/types';

/** Moderator queue: posts on review and posts with open reports. Every decision is logged on the server. */
export default function ModerationScreen() {
  const c = usePalette();
  const { user } = useAuth();
  const [items, setItems] = useState<QueueItem[]>([]);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await api.moderationQueue());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Нет связи с сервером');
    } finally {
      setLoading(false);
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load]),
  );

  async function act(item: QueueItem, action: 'approve' | 'hide' | 'delete', banDays?: number) {
    const run = async () => {
      try {
        await api.moderate(item.id, action, (notes[item.id] ?? '').trim(), banDays);
        setItems((xs) => xs.filter((x) => x.id !== item.id));
      } catch (e) {
        RNAlert.alert('Не получилось', e instanceof ApiError ? e.message : 'Нет связи с сервером');
      }
    };
    if (action === 'approve') return run();
    const what = action === 'delete' ? 'Удалить наблюдение навсегда?' : banDays ? `Скрыть и заблокировать автора на ${banDays} дн.?` : 'Скрыть наблюдение?';
    RNAlert.alert(what, 'Решение записывается в журнал модерации.', [
      { text: 'Отмена', style: 'cancel' },
      { text: 'Да', style: 'destructive', onPress: run },
    ]);
  }

  if (user && user.role === 'user') {
    return (
      <View style={{ flex: 1, padding: 16, backgroundColor: c.bg }}>
        <ErrorBox message="Этот раздел только для модераторов." onRetry={() => router.back()} />
      </View>
    );
  }

  return (
    <FlatList
      style={{ backgroundColor: c.bg }}
      contentContainerStyle={{ padding: 16, gap: 14 }}
      data={items}
      keyExtractor={(x) => String(x.id)}
      refreshing={loading}
      onRefresh={load}
      ListHeaderComponent={error ? <ErrorBox message={error} onRetry={load} /> : undefined}
      ListEmptyComponent={
        !loading && !error ? (
          <Card>
            <Text style={{ color: c.muted }}>Очередь пуста: нет постов на проверке и новых жалоб.</Text>
          </Card>
        ) : undefined
      }
      renderItem={({ item }) => (
        <View style={{ gap: 8 }}>
          <ObservationCard o={item} showZone />
          <Card style={{ gap: 6 }}>
            <Text style={{ color: c.ink, fontWeight: '800' }}>
              Автор: {item.author_name}
              {item.author_banned_until ? ' · сейчас заблокирован' : ''}
            </Text>
            {item.moderation_reason && <Text style={{ color: c.riskInk, fontWeight: '700' }}>Почему здесь: {item.moderation_reason}</Text>}
            {item.reports.map((r, i) => (
              <Text key={i} style={{ color: c.ink, fontSize: 13 }}>
                • {r.reason}
                {r.comment ? `: «${r.comment}»` : ''}
              </Text>
            ))}
            <TextInput
              value={notes[item.id] ?? ''}
              onChangeText={(t) => setNotes((n) => ({ ...n, [item.id]: t }))}
              placeholder="Пояснение для журнала и автора"
              placeholderTextColor={c.muted}
              maxLength={300}
              style={[s.input, { color: c.ink, borderColor: c.line2 }]}
            />
            <View style={s.row}>
              <Btn label="Одобрить" color={c.okInk} onPress={() => act(item, 'approve')} />
              <Btn label="Скрыть" color={c.riskInk} onPress={() => act(item, 'hide')} />
            </View>
            <View style={s.row}>
              <Btn label="Скрыть + бан 7 дн." color={c.dangerInk} onPress={() => act(item, 'hide', 7)} />
              <Btn label="Удалить" color={c.dangerInk} onPress={() => act(item, 'delete')} />
            </View>
          </Card>
        </View>
      )}
    />
  );
}

function Btn({ label, color, onPress }: { label: string; color: string; onPress: () => void }) {
  const c = usePalette();
  return (
    <Pressable onPress={onPress} style={[s.btn, { borderColor: c.line2, backgroundColor: c.surface }]} accessibilityRole="button">
      <Text style={{ color, fontWeight: '800', fontSize: 13 }}>{label}</Text>
    </Pressable>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', gap: 8 },
  btn: { flex: 1, minHeight: 44, borderWidth: 1, borderRadius: 12, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 6 },
  input: { minHeight: 44, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12 },
});
