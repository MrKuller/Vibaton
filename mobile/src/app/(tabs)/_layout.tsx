import { Tabs } from 'expo-router/js-tabs';
import Svg, { Circle, Path } from 'react-native-svg';

import { usePalette } from '@/lib/theme';

import type { ColorValue } from 'react-native';

type IconProps = { color: ColorValue };

const icons = {
  map: ({ color }: IconProps) => (
    <Svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke={color as string} strokeWidth={2} strokeLinejoin="round">
      <Path d="M9 4l-6 2v14l6-2 6 2 6-2V4l-6 2z" />
      <Path d="M9 4v14M15 6v14" />
    </Svg>
  ),
  feed: ({ color }: IconProps) => (
    <Svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke={color as string} strokeWidth={2} strokeLinecap="round">
      <Path d="M4 6h16M4 12h16M4 18h10" />
    </Svg>
  ),
  weather: ({ color }: IconProps) => (
    <Svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke={color as string} strokeWidth={2} strokeLinecap="round">
      <Path d="M3 8h12a3 3 0 1 0-3-3" />
      <Path d="M3 12h16a3 3 0 1 1-3 3" />
      <Path d="M3 16h8" />
    </Svg>
  ),
  profile: ({ color }: IconProps) => (
    <Svg width={24} height={24} viewBox="0 0 24 24" fill="none" stroke={color as string} strokeWidth={2} strokeLinecap="round">
      <Circle cx={12} cy={8} r={4} />
      <Path d="M4 21c1-4 4-6 8-6s7 2 8 6" />
    </Svg>
  ),
};

export default function TabsLayout() {
  const c = usePalette();
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: c.accent,
        tabBarInactiveTintColor: c.muted,
        tabBarStyle: { backgroundColor: c.surface, borderTopColor: c.line },
        tabBarLabelStyle: { fontSize: 11, fontWeight: '700' },
        headerStyle: { backgroundColor: c.surface },
        headerTintColor: c.ink,
        headerTitleStyle: { fontWeight: '800' },
        sceneStyle: { backgroundColor: c.bg },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Карта', headerShown: false, tabBarIcon: icons.map }} />
      <Tabs.Screen name="feed" options={{ title: 'Лента', tabBarIcon: icons.feed }} />
      <Tabs.Screen name="weather" options={{ title: 'Погода', tabBarIcon: icons.weather }} />
      <Tabs.Screen name="profile" options={{ title: 'Профиль', tabBarIcon: icons.profile }} />
    </Tabs>
  );
}
