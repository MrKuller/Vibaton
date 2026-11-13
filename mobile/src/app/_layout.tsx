import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { AppState } from 'react-native';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { ConsentModal } from '@/components/ConsentModal';
import { flushQueue } from '@/lib/queue';
import { SettingsProvider } from '@/lib/settings';
import { usePalette } from '@/lib/theme';

export default function RootLayout() {
  const c = usePalette();

  // Send observations saved without network whenever the app comes back to the foreground.
  useEffect(() => {
    flushQueue().catch(() => undefined);
    const sub = AppState.addEventListener('change', (st) => st === 'active' && flushQueue().catch(() => undefined));
    return () => sub.remove();
  }, []);

  return (
    <SafeAreaProvider>
      <SettingsProvider>
        <StatusBar style="auto" />
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
          <Stack.Screen name="sos" options={{ headerShown: false, presentation: 'fullScreenModal' }} />
        </Stack>
        <ConsentModal />
      </SettingsProvider>
    </SafeAreaProvider>
  );
}
