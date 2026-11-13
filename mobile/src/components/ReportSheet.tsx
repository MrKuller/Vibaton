import { router } from 'expo-router';
import { useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, TextInput } from 'react-native';

import { api, ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { usePalette } from '@/lib/theme';
import type { Observation, ReportReason } from '@/lib/types';

import { Button } from './ui';

const REASONS: [ReportReason, string][] = [
  ['fake', 'Неправда или фейк'],
  ['spam', 'Спам или реклама'],
  ['insult', 'Оскорбления'],
  ['not_ice', 'Фото не про лёд'],
  ['personal', 'Личные данные: лица, номера, адреса'],
  ['other', 'Другое'],
];

/** "Пожаловаться": returns a function that opens the sheet and the sheet itself to render. */
export function useReportSheet(onDone?: (o: Observation) => void) {
  const c = usePalette();
  const { user } = useAuth();
  const [target, setTarget] = useState<Observation | null>(null);
  const [reason, setReason] = useState<ReportReason | null>(null);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState('');

  function open(o: Observation) {
    if (!user) return router.push('/login');
    setTarget(o);
    setReason(null);
    setComment('');
    setMsg('');
  }

  async function send() {
    if (!target || !reason) return;
    setBusy(true);
    try {
      const r = await api.report(target.id, reason, comment.trim());
      setMsg(r.message);
      onDone?.(target);
      setTimeout(() => setTarget(null), 1200);
    } catch (e) {
      setMsg(e instanceof ApiError ? e.message : 'Нет связи с сервером');
    } finally {
      setBusy(false);
    }
  }

  const sheet = (
    <Modal visible={!!target} transparent animationType="slide" onRequestClose={() => setTarget(null)}>
      <Pressable style={s.backdrop} onPress={() => setTarget(null)} accessibilityLabel="Закрыть">
        <Pressable style={[s.box, { backgroundColor: c.surface }]} onPress={() => undefined}>
          <Text style={{ color: c.ink, fontSize: 18, fontWeight: '800' }}>Пожаловаться</Text>
          <Text style={{ color: c.muted, fontSize: 13, lineHeight: 18 }}>
            После трёх жалоб от разных людей текст и фото скрываются до проверки модератором. Сигнал об опасности при
            этом остаётся на карте.
          </Text>
          {REASONS.map(([k, label]) => (
            <Pressable
              key={k}
              onPress={() => setReason(k)}
              style={[s.option, { borderColor: reason === k ? c.accent : c.line2, backgroundColor: reason === k ? c.accentBg : c.surface }]}
              accessibilityRole="radio"
              accessibilityState={{ checked: reason === k }}
            >
              <Text style={{ color: reason === k ? c.accentInk : c.ink, fontWeight: reason === k ? '800' : '600' }}>{label}</Text>
            </Pressable>
          ))}
          <TextInput
            value={comment}
            onChangeText={setComment}
            placeholder="Пояснение (необязательно)"
            placeholderTextColor={c.muted}
            maxLength={300}
            style={[s.input, { color: c.ink, borderColor: c.line2 }]}
          />
          {!!msg && <Text style={{ color: c.ink, fontWeight: '700' }}>{msg}</Text>}
          <Button title="Отправить жалобу" disabled={!reason} loading={busy} onPress={send} />
        </Pressable>
      </Pressable>
    </Modal>
  );
  return { open, sheet };
}

const s = StyleSheet.create({
  backdrop: { flex: 1, backgroundColor: 'rgba(6,14,22,0.55)', justifyContent: 'flex-end' },
  box: { borderTopLeftRadius: 22, borderTopRightRadius: 22, padding: 20, gap: 10 },
  option: { minHeight: 44, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, justifyContent: 'center' },
  input: { minHeight: 44, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12 },
});
