import { Image, Pressable, StyleSheet, Text, View } from 'react-native';

import { photoUrl } from '@/lib/api';
import { agoMin } from '@/lib/format';
import { usePalette } from '@/lib/theme';
import type { Observation, ReactionKind } from '@/lib/types';

import { Card } from './ui';

const REACTIONS: [ReactionKind, string][] = [
  ['confirm', 'Подтверждаю'],
  ['changed', 'Изменилось'],
  ['wrong', 'Неверно'],
];

export function ObservationCard({
  o,
  showZone,
  onReact,
  onDelete,
  onOpenZone,
}: {
  o: Observation;
  showZone?: boolean;
  onReact?: (o: Observation, kind: ReactionKind) => void;
  onDelete?: (o: Observation) => void;
  onOpenZone?: (zoneId: string) => void;
}) {
  const c = usePalette();
  const sevColor = o.severity === 'danger' ? c.danger : o.severity === 'risk' ? c.riskEdge : c.clearEdge;
  const old = o.freshness === 'old';
  const title = o.type_label + (o.thickness_cm != null ? ` · лёд ${o.thickness_cm} см` : '');
  const meta = [o.method, o.ice_type].filter(Boolean).join(', ');
  const img = photoUrl(o.photo_url);

  return (
    <Card
      style={[
        o.freshness !== 'fresh' && { backgroundColor: c.surface2, borderStyle: 'dashed', borderColor: c.line2 },
        o.excluded && { opacity: 0.7 },
      ]}
    >
      {img && <Image source={{ uri: img }} style={s.photo} accessibilityLabel={`Фото: ${o.type_label}`} />}
      <View style={s.row}>
        <View style={[s.sev, { backgroundColor: sevColor }]} />
        <Text style={[s.title, { color: c.ink }]} numberOfLines={2}>
          {title}
        </Text>
        <Text style={{ color: c.muted, fontSize: 12, fontWeight: '600' }}>
          {agoMin(o.age_min)}
          {old ? ' · устарело' : ''}
        </Text>
      </View>
      {showZone && (
        <Pressable onPress={() => onOpenZone?.(o.zone_id)} accessibilityRole="link">
          <Text style={{ color: c.accent, fontWeight: '700', fontSize: 13 }}>{o.zone_name}</Text>
        </Pressable>
      )}
      {(meta || o.text) && (
        <Text style={{ color: c.ink, fontSize: 14, lineHeight: 20 }}>{[meta, o.text].filter(Boolean).join('. ')}</Text>
      )}
      <Text style={{ fontSize: 12, fontWeight: '700', color: o.onsite ? c.okInk : c.riskInk }}>
        {o.onsite
          ? `✓ Снято на месте${o.gps_accuracy_m ? ` · GPS ±${Math.round(o.gps_accuracy_m)} м` : ''}`
          : 'Не на месте или неточный GPS'}
        {` · подтвердили ${o.counts.confirm}`}
      </Text>
      <Text style={{ fontSize: 12, color: c.muted }}>
        {o.mine ? 'Ваше наблюдение' : o.author}
        {o.counts.changed ? ` · «изменилось»: ${o.counts.changed}` : ''}
        {o.counts.wrong ? ` · «неверно»: ${o.counts.wrong}` : ''}
        {o.ai_tags.length ? ` · ИИ: ${o.ai_tags.join(', ')}` : ''}
      </Text>
      {o.excluded && (
        <Text style={{ fontSize: 12, color: c.muted, fontWeight: '700' }}>
          {old ? 'Старше суток: не учитывается в статусе участка.' : 'Отмечено как неверное, не учитывается.'}
        </Text>
      )}
      {o.mine
        ? onDelete && (
            <Pressable onPress={() => onDelete(o)} style={[s.react, { borderColor: c.line2, alignSelf: 'flex-start', paddingHorizontal: 14 }]}>
              <Text style={{ color: c.ink, fontWeight: '700', fontSize: 12 }}>Удалить</Text>
            </Pressable>
          )
        : onReact && (
            <View style={s.reacts} accessibilityRole="radiogroup" accessibilityLabel="Оценить наблюдение">
              {REACTIONS.map(([k, label]) => {
                const on = o.my_reaction === k;
                return (
                  <Pressable
                    key={k}
                    accessibilityRole="radio"
                    accessibilityState={{ checked: on }}
                    onPress={() => onReact(o, k)}
                    style={[s.react, { borderColor: on ? c.accent : c.line2, backgroundColor: on ? c.accentBg : c.surface }]}
                  >
                    <Text style={{ color: on ? c.accentInk : c.ink, fontWeight: '700', fontSize: 12 }}>{label}</Text>
                  </Pressable>
                );
              })}
            </View>
          )}
    </Card>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sev: { width: 10, height: 10, borderRadius: 3 },
  title: { flex: 1, fontWeight: '800', fontSize: 14 },
  photo: { width: '100%', aspectRatio: 16 / 9, borderRadius: 12 },
  reacts: { flexDirection: 'row', gap: 6 },
  react: { flex: 1, minHeight: 44, borderWidth: 1, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
});
