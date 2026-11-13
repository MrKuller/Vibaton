import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';

import { LEVEL_WORD, levelColors, usePalette } from '@/lib/theme';
import type { Level } from '@/lib/types';

export function StatusPill({ level }: { level: Level }) {
  const c = usePalette();
  const lc = levelColors(c, level);
  return (
    <View
      style={[
        s.pill,
        { backgroundColor: lc.pill },
        level === 'nodata' && { borderWidth: 1, borderStyle: 'dashed', borderColor: c.muted },
      ]}
    >
      <Text style={[s.pillText, { color: lc.pillText }]}>{LEVEL_WORD[level].toUpperCase()}</Text>
    </View>
  );
}

export function Button({
  title,
  onPress,
  disabled,
  variant = 'primary',
  loading,
  style,
}: {
  title: string;
  onPress: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'ghost';
  loading?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const c = usePalette();
  const primary = variant === 'primary';
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!disabled }}
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [
        s.btn,
        primary ? { backgroundColor: c.accent } : { backgroundColor: c.surface, borderWidth: 1, borderColor: c.line2 },
        (disabled || pressed) && { opacity: disabled ? 0.45 : 0.85 },
        style,
      ]}
    >
      {loading ? (
        <ActivityIndicator color={primary ? c.onAccent : c.ink} />
      ) : (
        <Text style={[s.btnText, { color: primary ? c.onAccent : c.ink }]}>{title}</Text>
      )}
    </Pressable>
  );
}

export function Chip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  const c = usePalette();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[
        s.chip,
        selected ? { backgroundColor: c.ink, borderColor: c.ink } : { backgroundColor: c.surface, borderColor: c.line2 },
      ]}
    >
      <Text style={{ color: selected ? c.bg : c.ink, fontWeight: selected ? '700' : '600', fontSize: 13 }}>{label}</Text>
    </Pressable>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const c = usePalette();
  return <View style={[s.card, { backgroundColor: c.surface, borderColor: c.line }, style]}>{children}</View>;
}

export function Disclaimer({ children }: { children?: ReactNode }) {
  const c = usePalette();
  return (
    <Text style={{ fontSize: 11, color: c.muted, textAlign: 'center', lineHeight: 15 }}>
      {children ?? 'Приложение не гарантирует безопасность льда и не оценивает его прочность.'}
    </Text>
  );
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  const c = usePalette();
  return (
    <Card style={{ borderColor: c.danger }}>
      <Text style={{ color: c.ink, fontWeight: '700' }}>{message}</Text>
      {onRetry && <Button title="Повторить" variant="ghost" onPress={onRetry} />}
    </Card>
  );
}

const s = StyleSheet.create({
  pill: { paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, alignSelf: 'flex-start' },
  pillText: { fontSize: 11, fontWeight: '800', letterSpacing: 0.4 },
  btn: { minHeight: 52, borderRadius: 14, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 16 },
  btnText: { fontSize: 16, fontWeight: '800' },
  chip: { height: 38, paddingHorizontal: 14, borderRadius: 999, borderWidth: 1, justifyContent: 'center' },
  card: { borderWidth: 1, borderRadius: 16, padding: 14, gap: 8 },
});
