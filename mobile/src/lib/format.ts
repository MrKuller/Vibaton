export function plural(n: number, one: string, few: string, many: string) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b > 1 && b < 5) return few;
  if (b === 1) return one;
  return many;
}

export function agoMin(m: number) {
  if (m < 1) return 'только что';
  if (m < 60) return `${m} мин назад`;
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h < 6) return `${h} ч${r ? ` ${r} мин` : ''} назад`;
  if (h < 48) return `${h} ч назад`;
  return `${Math.floor(h / 24)} дн назад`;
}

export function ago(iso: string | null) {
  if (!iso) return 'нет наблюдений';
  return agoMin(Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 60000)));
}

export function km(x: number) {
  return (x < 10 ? x.toFixed(1) : Math.round(x).toString()).replace('.', ',') + ' км';
}

export function hhmm(d: Date) {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

export function leftText(ms: number) {
  const m = Math.ceil(Math.abs(ms) / 60000);
  const h = Math.floor(m / 60);
  return (h ? `${h} ч ` : '') + `${m % 60} мин`;
}
