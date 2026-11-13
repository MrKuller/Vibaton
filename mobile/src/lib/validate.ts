/**
 * "Защита от дурака" on the phone: the same rules as the server (backend/app/auth.py),
 * checked while typing, so a person sees what to fix before pressing the button.
 * The server checks everything again: these functions only save a round trip.
 */

const DOMAIN_TYPOS: Record<string, string> = {
  'gmail.con': 'gmail.com', 'gmail.co': 'gmail.com', 'gmail.cm': 'gmail.com', 'gmial.com': 'gmail.com',
  'gmai.com': 'gmail.com', 'gamil.com': 'gmail.com', 'gmail.ru': 'gmail.com',
  'mail.ry': 'mail.ru', 'mail.ro': 'mail.ru', 'mial.ru': 'mail.ru', 'mali.ru': 'mail.ru', 'mail.r': 'mail.ru',
  'yandex.ry': 'yandex.ru', 'yandex.ri': 'yandex.ru', 'yandx.ru': 'yandex.ru', 'yadex.ru': 'yandex.ru',
  'yndex.ru': 'yandex.ru', 'ya.ry': 'ya.ru', 'bk.ry': 'bk.ru', 'inbox.ry': 'inbox.ru', 'list.ry': 'list.ru',
  'rambler.ry': 'rambler.ru', 'ramler.ru': 'rambler.ru', 'outlook.con': 'outlook.com',
};
const COMMON = new Set([
  'password', 'password1', 'password123', 'qwerty123', 'qwertyuiop', 'qwerty12', '1q2w3e4r', '1q2w3e4r5t',
  'zaq12wsx', 'abc12345', 'abcd1234', 'admin123', 'passw0rd', 'p@ssw0rd', 'qwerty1234', '1qaz2wsx',
  'q1w2e3r4', 'asdf1234', 'zxcvbnm1', 'йцукен123', 'пароль123', '11111111a',
]);
const RESERVED = /admin|админ|moder|модер|мчс|mchs|поддержк|support|оператор|официальн|official/i;

export function normalizeEmail(raw: string) {
  return raw.trim().toLowerCase().replace(/\s+/g, '');
}

/** null = OK */
export function checkEmail(raw: string): string | null {
  const email = normalizeEmail(raw);
  if (!email) return 'Введите email';
  if (!email.includes('@')) return 'В email не хватает знака @. Пример: ivan@mail.ru';
  if (/[а-яё]/i.test(email)) return 'Email пишется латиницей. Проверьте раскладку клавиатуры.';
  const domain = email.split('@').pop() ?? '';
  if (DOMAIN_TYPOS[domain]) return `Похоже на опечатку: вы имели в виду @${DOMAIN_TYPOS[domain]}?`;
  if (email.includes('..') || !/^[^@\s]+@[a-z0-9-]+(\.[a-z0-9-]+)*\.[a-z]{2,}$/.test(email))
    return 'Проверьте email: например, ivan@mail.ru';
  return null;
}

export function fixEmailTypo(raw: string): string | null {
  const email = normalizeEmail(raw);
  const domain = email.split('@').pop() ?? '';
  return DOMAIN_TYPOS[domain] ? email.replace(/@[^@]+$/, '@' + DOMAIN_TYPOS[domain]) : null;
}

export function checkName(raw: string): string | null {
  const name = raw.trim().replace(/\s+/g, ' ');
  const letters = (name.match(/[A-Za-zА-Яа-яЁё]/g) ?? []).length;
  if (!name) return 'Введите имя: его увидят в ленте, если вы публикуете не анонимно';
  if (name.length < 2 || name.length > 40 || letters < 2) return 'Имя: от 2 до 40 символов, хотя бы 2 буквы';
  if (!/^[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9 .'-]*$/.test(name)) return 'В имени можно использовать буквы, цифры, пробел и дефис';
  if (RESERVED.test(name)) return 'Такое имя нельзя: оно похоже на служебное или официальное';
  if (/(https?:|www\.|\.ru\b|\.com\b|@)/i.test(name)) return 'В имени не должно быть ссылок и адресов';
  return null;
}

export function checkPassword(pw: string, email: string, name: string): string | null {
  if (pw.length < 8) return `Пароль: ещё ${8 - pw.length} ${pw.length === 7 ? 'символ' : 'символа'} минимум`;
  if (pw.length > 128) return 'Пароль: не больше 128 символов';
  if (!/[A-Za-zА-Яа-яЁё]/.test(pw) || !/\d/.test(pw)) return 'В пароле нужны и буквы, и цифры';
  const low = pw.toLowerCase();
  if (COMMON.has(low) || /(.)\1{3,}/.test(pw) || low.includes('12345678') || low.includes('qwertyui'))
    return 'Пароль слишком простой. Придумайте другой.';
  const local = normalizeEmail(email).split('@')[0];
  const n = name.trim().toLowerCase().replace(/\s/g, '');
  if ((local.length >= 4 && low.includes(local)) || (n.length >= 2 && low.includes(n)))
    return 'Пароль не должен содержать email или имя';
  return null;
}

export function passwordStrength(pw: string): 0 | 1 | 2 | 3 {
  let s = 0;
  if (pw.length >= 8) s++;
  if (pw.length >= 12) s++;
  if (/[^A-Za-zА-Яа-яЁё0-9]/.test(pw) || (/[a-zа-я]/.test(pw) && /[A-ZА-Я]/.test(pw))) s++;
  return Math.min(3, s) as 0 | 1 | 2 | 3;
}
