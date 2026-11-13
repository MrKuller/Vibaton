import { useColorScheme } from 'react-native';

import type { Level } from './types';

const light = {
  bg: '#F4F8FB',
  surface: '#FFFFFF',
  surface2: '#EEF3F8',
  ink: '#0B1B2B',
  muted: '#4A5B6C',
  line: '#E1E8EF',
  line2: '#C9D4DE',
  accent: '#1D5FD1',
  accentInk: '#123F8F',
  accentBg: '#E8F0FD',
  onAccent: '#FFFFFF',
  danger: '#B3261E',
  dangerInk: '#7A120D',
  dangerBg: '#FCE9E8',
  risk: '#F5B451',
  riskEdge: '#B86A00',
  riskInk: '#6B3D00',
  riskBg: '#FFF1DC',
  riskOn: '#3D2300',
  okInk: '#1F5B2E',
  okBg: '#E6F4EA',
  clear: '#9CC3EE',
  clearEdge: '#2F6FB5',
  nodata: '#8A97A5',
  night: '#0B1B2B',
  nightMuted: '#B7C6D6',
  nightLine: '#3A4E63',
  sos: '#8E1B15',
};

const dark: typeof light = {
  ...light,
  bg: '#0E1823',
  surface: '#16232F',
  surface2: '#1E2E3D',
  ink: '#E8EFF6',
  muted: '#9EB0C2',
  line: '#263646',
  line2: '#34485C',
  accent: '#6EA0F5',
  accentInk: '#A9C6FA',
  accentBg: '#1A2C47',
  onAccent: '#0B1B2B',
  danger: '#E0574D',
  dangerInk: '#FFB4AE',
  dangerBg: '#3A1714',
  riskEdge: '#F5B451',
  riskInk: '#F7C77A',
  riskBg: '#33250F',
  okInk: '#86D69E',
  okBg: '#15301E',
  clear: '#5C8DC4',
  clearEdge: '#9CC3EE',
  nodata: '#5D6B79',
  night: '#060E16',
  nightLine: '#2A3D52',
};

export type Palette = typeof light;

export function usePalette(): Palette {
  return useColorScheme() === 'dark' ? dark : light;
}

/** Map fills: no green anywhere. "No data" is grey with a dashed outline. */
export function levelColors(c: Palette, level: Level) {
  switch (level) {
    case 'danger':
      return { fill: 'rgba(179,38,30,0.55)', stroke: '#7A120D', pill: c.danger, pillText: '#FFFFFF', dashed: false };
    case 'risk':
      return { fill: 'rgba(245,180,81,0.6)', stroke: '#B86A00', pill: c.risk, pillText: c.riskOn, dashed: false };
    case 'clear':
      return { fill: 'rgba(156,195,238,0.55)', stroke: '#2F6FB5', pill: c.clear, pillText: '#0B1B2B', dashed: false };
    default:
      return { fill: 'rgba(138,151,165,0.35)', stroke: '#5D6B79', pill: c.surface2, pillText: c.ink, dashed: true };
  }
}

export const LEVEL_WORD: Record<Level, string> = {
  danger: 'Опасно',
  risk: 'Есть риск',
  clear: 'Тревог нет',
  nodata: 'Нет данных',
};
