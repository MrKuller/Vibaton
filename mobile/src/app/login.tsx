import { router, Stack } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Button } from '@/components/ui';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth';
import { usePalette } from '@/lib/theme';
import { checkEmail, checkName, checkPassword, fixEmailTypo, normalizeEmail, passwordStrength } from '@/lib/validate';

type Field = 'email' | 'password' | 'repeat' | 'name';

export default function LoginScreen() {
  const c = usePalette();
  const { login, register } = useAuth();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [name, setName] = useState('');
  const [show, setShow] = useState(false);
  const [touched, setTouched] = useState<Partial<Record<Field, boolean>>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState('');

  const reg = mode === 'register';
  const errors: Partial<Record<Field, string | null>> = {
    email: checkEmail(email),
    password: reg ? checkPassword(password, email, name) : password ? null : 'Введите пароль',
    repeat: reg ? (repeat !== password ? 'Пароли не совпадают' : null) : null,
    name: reg ? checkName(name) : null,
  };
  const invalid = Object.values(errors).some(Boolean);
  const shown = (f: Field) => (touched[f] ? errors[f] : null);
  const typoFix = fixEmailTypo(email);
  const strength = passwordStrength(password);

  async function submit() {
    setTouched({ email: true, password: true, repeat: true, name: true });
    setErr('');
    if (invalid) return;
    setBusy(true);
    try {
      if (reg) await register(normalizeEmail(email), password, name.trim().replace(/\s+/g, ' '));
      else await login(normalizeEmail(email), password);
      if (router.canGoBack()) router.back();
      else router.replace('/');
    } catch (e) {
      setErr(e instanceof ApiError ? e.message : 'Нет связи с сервером. Проверьте интернет и адрес сервера в mobile/.env.');
    } finally {
      setBusy(false);
    }
  }

  const input = (f: Field) => [
    s.input,
    { color: c.ink, borderColor: shown(f) ? c.danger : c.line2, backgroundColor: c.surface },
  ];
  const hint = (f: Field) =>
    shown(f) ? (
      <Text style={{ color: c.danger, fontSize: 13, fontWeight: '600' }} accessibilityLiveRegion="polite">
        {shown(f)}
      </Text>
    ) : null;

  return (
    <KeyboardAvoidingView style={{ flex: 1, backgroundColor: c.bg }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Stack.Screen options={{ title: reg ? 'Регистрация' : 'Вход' }} />
      <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }} keyboardShouldPersistTaps="handled">
        <View style={[s.seg, { backgroundColor: c.surface2 }]}>
          {(['login', 'register'] as const).map((m) => (
            <Pressable
              key={m}
              onPress={() => {
                setMode(m);
                setErr('');
                setTouched({});
              }}
              style={[s.segBtn, mode === m && { backgroundColor: c.surface }]}
              accessibilityRole="tab"
              accessibilityState={{ selected: mode === m }}
            >
              <Text style={{ color: mode === m ? c.ink : c.muted, fontWeight: mode === m ? '800' : '600' }}>
                {m === 'login' ? 'Вход' : 'Регистрация'}
              </Text>
            </Pressable>
          ))}
        </View>
        <Text style={{ color: c.muted, fontSize: 13, lineHeight: 19 }}>
          Смотреть карту можно без аккаунта. Аккаунт нужен, чтобы публиковать наблюдения и подтверждать чужие.
        </Text>

        {reg && (
          <View style={s.field}>
            <Text style={[s.label, { color: c.ink }]}>Имя в ленте</Text>
            <TextInput
              value={name}
              onChangeText={setName}
              onBlur={() => setTouched((t) => ({ ...t, name: true }))}
              placeholder="Например, Сергей"
              placeholderTextColor={c.muted}
              style={input('name')}
              maxLength={40}
              autoComplete="name"
            />
            {hint('name')}
          </View>
        )}

        <View style={s.field}>
          <Text style={[s.label, { color: c.ink }]}>Email</Text>
          <TextInput
            value={email}
            onChangeText={setEmail}
            onBlur={() => setTouched((t) => ({ ...t, email: true }))}
            placeholder="ivan@mail.ru"
            placeholderTextColor={c.muted}
            style={input('email')}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            keyboardType="email-address"
            maxLength={254}
          />
          {hint('email')}
          {typoFix && (
            <Pressable onPress={() => setEmail(typoFix)} accessibilityRole="button">
              <Text style={{ color: c.accent, fontWeight: '700' }}>Исправить на {typoFix}</Text>
            </Pressable>
          )}
        </View>

        <View style={s.field}>
          <Text style={[s.label, { color: c.ink }]}>Пароль</Text>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <TextInput
              value={password}
              onChangeText={setPassword}
              onBlur={() => setTouched((t) => ({ ...t, password: true }))}
              placeholder={reg ? '8+ символов, буквы и цифры' : 'Пароль'}
              placeholderTextColor={c.muted}
              style={[input('password'), { flex: 1 }]}
              secureTextEntry={!show}
              autoCapitalize="none"
              autoCorrect={false}
              autoComplete={reg ? 'new-password' : 'current-password'}
              maxLength={128}
            />
            <Pressable onPress={() => setShow((v) => !v)} hitSlop={8} accessibilityRole="button"
              accessibilityLabel={show ? 'Скрыть пароль' : 'Показать пароль'}>
              <Text style={{ color: c.accent, fontWeight: '700' }}>{show ? 'Скрыть' : 'Показать'}</Text>
            </Pressable>
          </View>
          {reg && password.length > 0 && !errors.password && (
            <Text style={{ color: strength >= 2 ? c.okInk : c.riskInk, fontSize: 13, fontWeight: '600' }}>
              {strength >= 3 ? 'Надёжный пароль' : strength === 2 ? 'Хороший пароль' : 'Подойдёт, но длиннее надёжнее'}
            </Text>
          )}
          {hint('password')}
        </View>

        {reg && (
          <View style={s.field}>
            <Text style={[s.label, { color: c.ink }]}>Повторите пароль</Text>
            <TextInput
              value={repeat}
              onChangeText={setRepeat}
              onBlur={() => setTouched((t) => ({ ...t, repeat: true }))}
              placeholder="Ещё раз тот же пароль"
              placeholderTextColor={c.muted}
              style={input('repeat')}
              secureTextEntry={!show}
              autoCapitalize="none"
              autoCorrect={false}
              maxLength={128}
            />
            {hint('repeat')}
          </View>
        )}

        {!!err && (
          <Text style={{ color: c.danger, fontWeight: '700' }} accessibilityLiveRegion="polite">
            {err}
          </Text>
        )}
        <Button title={reg ? 'Зарегистрироваться' : 'Войти'} loading={busy} onPress={submit} />
        {reg && (
          <Text style={{ color: c.muted, fontSize: 12, lineHeight: 17 }}>
            Регистрируясь, вы соглашаетесь на обработку email, геолокации и фото для работы приложения. Приложение не
            гарантирует безопасность льда.
          </Text>
        )}
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  seg: { flexDirection: 'row', borderRadius: 12, padding: 4, gap: 4 },
  segBtn: { flex: 1, height: 44, borderRadius: 9, alignItems: 'center', justifyContent: 'center' },
  field: { gap: 6 },
  label: { fontSize: 14, fontWeight: '800' },
  input: { minHeight: 50, borderWidth: 1, borderRadius: 12, paddingHorizontal: 12, fontSize: 16 },
});
