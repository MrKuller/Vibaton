import { useState } from 'react';
import { Modal, ScrollView, StyleSheet, Switch, Text, View } from 'react-native';

import { useSettings } from '@/lib/settings';
import { usePalette } from '@/lib/theme';

import { Button } from './ui';

/** First launch: the disclaimer is accepted explicitly, not hidden in terms of use. */
export function ConsentModal() {
  const { settings, ready, update } = useSettings();
  const [ok, setOk] = useState(false);
  const c = usePalette();
  if (!ready || settings.consent) return null;
  return (
    <Modal animationType="slide" transparent visible>
      <View style={s.backdrop}>
        <ScrollView style={[s.box, { backgroundColor: c.surface }]} contentContainerStyle={{ gap: 12, padding: 20 }}>
          <Text style={[s.h, { color: c.ink }]}>Перед началом</Text>
          <Text style={{ color: c.ink, fontSize: 15, lineHeight: 22 }}>
            «Крепкий лёд» собирает сообщения рыбаков, прогноз погоды и запреты МЧС.{' '}
            <Text style={{ fontWeight: '800' }}>Приложение не гарантирует, что лёд выдержит,</Text> и не оценивает его
            прочность.
          </Text>
          {[
            'На карте нет зелёного цвета: «тревог нет» не значит «безопасно».',
            'Серый пунктир — свежих данных нет, обстановка неизвестна.',
            'Наблюдение свежее 6 часов (3 часа в оттепель и сильный ветер), через сутки перестаёт влиять на статус.',
          ].map((t) => (
            <Text key={t} style={{ color: c.ink, fontSize: 14, lineHeight: 20 }}>
              • {t}
            </Text>
          ))}
          <View style={s.row}>
            <Text style={{ flex: 1, color: c.ink, fontSize: 14, fontWeight: '600' }}>
              Понимаю и согласен на обработку геолокации и фото для работы приложения
            </Text>
            <Switch value={ok} onValueChange={setOk} accessibilityLabel="Согласие" />
          </View>
          <Button title="Продолжить" disabled={!ok} onPress={() => update({ consent: true })} />
        </ScrollView>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(6,14,22,0.55)', justifyContent: 'flex-end' },
  box: { borderTopLeftRadius: 22, borderTopRightRadius: 22, maxHeight: '90%' },
  h: { fontSize: 22, fontWeight: '800' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12 },
});
