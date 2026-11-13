import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ConsentModal } from '@/components/ConsentModal';
import { AuthProvider } from '@/lib/auth';
import { flushQueue } from '@/lib/queue';
import { SettingsProvider } from '@/lib/settings';
import { useIsDark, usePalette } from '@/lib/theme';

function AppStack() {
  const c = usePalette();
  const dark = useIsDark();
  return (
    <>
      <StatusBar style={dark ? 'light' : 'dark'} />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: c.surface },
          headerTintColor: c.ink,
          headerTitleStyle: { fontWeight: '800' },
          contentStyle: { backgroundColor: c.bg },
          headerBackTitle: 'Назад',
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="zone/[id]" options={{ title: 'Участок' }} />
        <Stack.Screen name="add" options={{ title: 'Новое наблюдение', presentation: 'modal' }} />
        <Stack.Screen name="login" options={{ title: 'Вход', presentation: 'modal' }} />
        <Stack.Screen name="moderation" options={{ title: 'Модерация' }} />
        <Stack.Screen name="sos" options={{ headerShown: false, presentation: 'fullScreenModal' }} />
      </Stack>
      <ConsentModal />
    </>
  );
}

export default function RootLayout() {
  // Send observations saved without network whenever the app comes back to the foreground.
  useEffect(() => {
    const sub = AppState.addEventListener('change', (st) => st === 'active' && flushQueue().catch(() => undefined));
    return () => sub.remove();
  }, []);

  return (
    <SafeAreaProvider>
      <SettingsProvider>
        <AuthProvider>
          <AppStack />
        </AuthProvider>
      </SettingsProvider>
    </SafeAreaProvider>
  );
}
