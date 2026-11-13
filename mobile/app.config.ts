import type { ExpoConfig } from 'expo/config';

// Map: Leaflet + OpenStreetMap in a WebView (src/components/IceMap.tsx). No API keys; works in Expo Go.
const config: ExpoConfig = {
  name: 'Крепкий лёд',
  slug: 'krepkiy-led',
  scheme: 'krepkiyled',
  version: '0.1.0',
  orientation: 'portrait',
  icon: './assets/icon.png',
  userInterfaceStyle: 'automatic',
  ios: {
    supportsTablet: false,
    bundleIdentifier: 'ru.krepkiyled.app',
  },
  android: {
    package: 'ru.krepkiyled.app',
    adaptiveIcon: {
      backgroundColor: '#E6F4FE',
      foregroundImage: './assets/android-icon-foreground.png',
      backgroundImage: './assets/android-icon-background.png',
      monochromeImage: './assets/android-icon-monochrome.png',
    },
    predictiveBackGestureEnabled: false,
  },
  web: { favicon: './assets/favicon.png' },
  plugins: [
    'expo-router',
    [
      'expo-location',
      {
        locationWhenInUsePermission:
          'Геолокация нужна, чтобы показать участки рядом и отметить, что наблюдение сделано на месте.',
      },
    ],
    [
      'expo-image-picker',
      {
        cameraPermission: 'Камера нужна, чтобы снять лёд для наблюдения.',
        photosPermission: false,
      },
    ],
    'expo-secure-store',
  ],
};

export default config;
