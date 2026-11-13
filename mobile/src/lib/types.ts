export type Level = 'danger' | 'risk' | 'clear' | 'nodata';
export type ObsType = 'crack' | 'hole' | 'water' | 'thin' | 'floe' | 'clear';
export type ReactionKind = 'confirm' | 'changed' | 'wrong';

export interface ZoneStatus {
  level: Level;
  label: string;
  advice: string;
  reasons: string[];
  fresh_count: number;
  fresh_window_h: number;
  last_observed_at: string | null;
  conflict: boolean;
  offshore_wind: boolean;
}

export interface LatLon {
  lat: number;
  lon: number;
}

export interface GeoPolygon {
  type: 'Polygon';
  coordinates: number[][][]; // [[[lon, lat], ...]]
}

export interface ZoneFeature {
  type: 'Feature';
  id: string;
  geometry: GeoPolygon;
  properties: {
    id: string;
    name: string;
    bay: string;
    ban: boolean;
    ban_text: string | null;
    center: LatLon;
    status: ZoneStatus;
  };
}

export interface ZoneCollection {
  type: 'FeatureCollection';
  features: ZoneFeature[];
}

export interface Observation {
  id: number;
  zone_id: string;
  zone_name: string;
  type: ObsType;
  type_label: string;
  severity: 'danger' | 'risk' | 'clear';
  thickness_cm: number | null;
  method: string | null;
  ice_type: string | null;
  text: string;
  lat: number | null;
  lon: number | null;
  onsite: boolean;
  gps_accuracy_m: number | null;
  author: string;
  photo_url: string | null;
  ai_hazard: string;
  ai_tags: string[];
  observed_at: string;
  age_min: number;
  freshness: 'fresh' | 'stale' | 'old';
  counts: Record<ReactionKind, number>;
  my_reaction: ReactionKind | null;
  mine: boolean;
  excluded: boolean;
}

export interface Weather {
  temp_c: number;
  wind_ms: number;
  wind_gust_ms: number | null;
  wind_from_deg: number;
  wind_from: string;
  days: { date: string; t_max: number | null; t_min: number | null }[];
  source: 'open-meteo' | 'fallback';
  crosses_zero: boolean;
  warming_c: number;
}

export interface ZoneDetail {
  id: string;
  name: string;
  bay: string;
  ban: boolean;
  ban_text: string | null;
  center: LatLon;
  geometry: GeoPolygon;
  status: ZoneStatus;
  weather: Weather;
  observations: Observation[];
}

export type Alert =
  | { kind: 'ban'; zone_id: string; zone_name: string; text: string; critical: true }
  | {
      kind: 'ai';
      critical: false;
      bay: string;
      text: string;
      facts: string[];
      observation_ids: number[];
      source: string;
      disclaimer: string;
    };

export interface NewObservation {
  type: ObsType;
  zone_id?: string;
  thickness_cm?: number | null;
  method?: string | null;
  ice_type?: string | null;
  text?: string;
  lat?: number;
  lon?: number;
  gps_accuracy_m?: number | null;
  mocked_location?: boolean;
  anonymous: boolean;
  author_name?: string | null;
  hide_point: boolean;
  observed_at?: string;
}
