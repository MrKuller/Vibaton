import * as Clipboard from 'expo-clipboard';
import { router } from 'expo-router';
import * as SMS from 'expo-sms';
import { useState } from 'react';
import { Linking, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useFix } from '@/lib/location';
import { useSettings } from '@/lib/settings';

const STEPS = {
  me: [
    'Не паникуйте и не снимайте одежду: она держит воздух.',
    'Развернитесь туда, откуда пришли: там лёд вас уже держал.',
    'Положите руки на лёд, работайте ногами, чтобы лечь горизонтально.',
    'Выползайте на лёд, откатитесь и ползите к берегу. Не вставайте.',
  ],
  other: [
    'Позвоните 112 или попросите позвонить других.',
    'Не подходите к пролому в рост. Подползайте лёжа, раскинув руки.',
    'Подайте шарф, ремень, доску или санки с 3–4 м. Руку не протягивайте.',
    'Тяните пострадавшего ползком к берегу, затем в тепло и сухую одежду.',
  ],
};

// Fixed colours on purpose: this screen looks the same in light and dark mode.
const RED = '#8E1B15';

export default function SosScreen() {
  const insets = useSafeAreaInsets();
  const { fix, state } = useFix();
  const { settings } = useSettings();
  const [tab, setTab] = useState<'me' | 'other'>('me');
  const [copied, setCopied] = useState(false);

  const coords = fix ? `${fix.lat.toFixed(5)}, ${fix.lon.toFixed(5)}` : null;
  const smsText = `Мне нужна помощь на льду. Координаты: ${coords ?? 'не определены'}`;

  async function sendSms() {
    if (!settings.onIce.contact) return router.push('/profile');
    if (await SMS.isAvailableAsync()) await SMS.sendSMSAsync([settings.onIce.contact], smsText);
  }

  return (
    <ScrollView style={{ backgroundColor: RED }} contentContainerStyle={[s.pad, { paddingTop: insets.top + 12, paddingBottom: insets.bottom + 24 }]}>
      <View style={s.row}>
        <Text style={s.h}>Экстренная помощь</Text>
        <Pressable onPress={() => router.back()} style={s.close} accessibilityLabel="Закрыть" hitSlop={8}>
          <Text style={{ color: '#fff', fontSize: 22, fontWeight: '700' }}>×</Text>
        </Pressable>
      </View>

      <Pressable style={s.call} onPress={() => Linking.openURL('tel:112')} accessibilityRole="button">
        <Text style={{ color: RED, fontSize: 24, fontWeight: '800' }}>Позвонить 112</Text>
      </Pressable>
      <Text style={s.note}>112 работает без SIM-карты и без денег на счёте.</Text>

      <View style={s.coords}>
        <Text style={s.note}>Ваши координаты — продиктуйте диспетчеру</Text>
        <Text style={s.big} selectable>
          {coords ?? (state === 'loading' ? 'Определяем…' : 'Геолокация недоступна')}
        </Text>
        {fix?.accuracy != null && <Text style={s.note}>GPS ±{Math.round(fix.accuracy)} м</Text>}
        {coords && (
          <Pressable
            style={s.outline}
            onPress={async () => {
              await Clipboard.setStringAsync(coords);
              setCopied(true);
            }}
          >
            <Text style={s.outlineText}>{copied ? 'Скопировано' : 'Скопировать координаты'}</Text>
          </Pressable>
        )}
      </View>

      <Pressable style={s.outline} onPress={sendSms}>
        <Text style={s.outlineText}>
          {settings.onIce.contact ? `SMS с координатами: ${settings.onIce.contact}` : 'Добавить экстренный контакт'}
        </Text>
      </Pressable>
      <Text style={s.note}>SMS уходит через обычную связь, мобильный интернет не нужен.</Text>

      <View style={s.tabs} accessibilityRole="tablist">
        {(['me', 'other'] as const).map((k) => (
          <Pressable key={k} onPress={() => setTab(k)} style={[s.tab, tab === k && { backgroundColor: '#fff' }]} accessibilityRole="tab" accessibilityState={{ selected: tab === k }}>
            <Text style={{ color: tab === k ? RED : '#fff', fontWeight: '800', fontSize: 14 }}>
              {k === 'me' ? 'Я провалился' : 'Человек в воде'}
            </Text>
          </Pressable>
        ))}
      </View>
      {STEPS[tab].map((t, i) => (
        <Text key={t} style={s.step}>
          {i + 1}. {t}
        </Text>
      ))}
    </ScrollView>
  );
}

const s = StyleSheet.create({
  pad: { paddingHorizontal: 16, gap: 14 },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  h: { color: '#fff', fontSize: 26, fontWeight: '800' },
  close: { width: 44, height: 44, borderRadius: 12, backgroundColor: 'rgba(255,255,255,0.18)', alignItems: 'center', justifyContent: 'center' },
  call: { minHeight: 84, borderRadius: 20, backgroundColor: '#fff', alignItems: 'center', justifyContent: 'center' },
  note: { color: '#fff', opacity: 0.9, fontSize: 12, fontWeight: '600' },
  coords: { backgroundColor: 'rgba(0,0,0,0.25)', borderRadius: 16, padding: 14, gap: 6 },
  big: { color: '#fff', fontSize: 26, fontWeight: '800' },
  outline: { minHeight: 52, borderRadius: 14, borderWidth: 2, borderColor: 'rgba(255,255,255,0.7)', alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  outlineText: { color: '#fff', fontWeight: '800', fontSize: 15, textAlign: 'center' },
  tabs: { flexDirection: 'row', gap: 6, backgroundColor: 'rgba(0,0,0,0.25)', borderRadius: 14, padding: 4 },
  tab: { flex: 1, minHeight: 46, borderRadius: 11, alignItems: 'center', justifyContent: 'center' },
  step: { color: '#fff', fontSize: 15, lineHeight: 22 },
});
