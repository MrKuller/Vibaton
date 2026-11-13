/**
 * Our own map: Leaflet + OpenStreetMap tiles inside a WebView. No Google, no Yandex, no API keys.
 *
 * The whole water area is a grid of H3 hexagons: ~0.74 km² in open water, ~0.1 km² along the shore,
 * ~0.015 km² on rivers. Cells without fresh reports are grey ("нет данных"); cells with a status are
 * coloured. Only H3 ids reach the page; h3-js (embedded) turns them into hexagons.
 *
 * - Leaflet is embedded in the app (src/vendor/leaflet.ts); only the tiles come from the network.
 * - Canvas rendering keeps ~850 polygons smooth on a phone.
 * - Tiles: EXPO_PUBLIC_MAP_TILE_URL (default: the public OpenStreetMap server, light use only).
 * - The attribution "© участники OpenStreetMap" must stay visible (bottom-right corner).
 */
import { useEffect, useMemo, useRef, useState, type ComponentType, type Ref } from 'react';
import { ActivityIndicator, StyleSheet, Text, View, type StyleProp, type ViewStyle } from 'react-native';
import { WebView, type WebViewMessageEvent, type WebViewProps } from 'react-native-webview';

import { levelColors, useIsDark, usePalette } from '@/lib/theme';
import type { CellStatus, GridCell, Place } from '@/lib/types';
import { H3_JS, LEAFLET_CSS, LEAFLET_JS } from '@/vendor/leaflet';

// react-native-webview's class typing (Props & undefined) collapses to `never` on TS 6; the runtime is fine.
type WebViewHandle = { injectJavaScript: (script: string) => void };
const MapWebView = WebView as unknown as ComponentType<WebViewProps & { ref?: Ref<WebViewHandle> }>;

const TILE_URL = process.env.EXPO_PUBLIC_MAP_TILE_URL || 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
const ATTRIBUTION =
  process.env.EXPO_PUBLIC_MAP_ATTRIBUTION ||
  '© <a href="https://www.openstreetmap.org/copyright">участники OpenStreetMap</a>';

export interface MapCluster {
  lat: number;
  lon: number;
  level: 'danger' | 'risk';
  text: string;
}

export interface MapFocus {
  lat: number;
  lon: number;
  zoom: number;
  /** change this number to re-center on the same point again */
  nonce: number;
}

interface Props {
  cells: GridCell[];
  statuses: Record<string, Pick<CellStatus, 'level'>>;
  places?: Place[];
  selectedId?: string | null;
  clusters?: MapCluster[];
  user?: { lat: number; lon: number } | null;
  focus?: MapFocus | null;
  initial: { lat: number; lon: number; zoom: number };
  interactive?: boolean;
  onSelectCell?: (id: string) => void;
  style?: StyleProp<ViewStyle>;
}

function buildHtml(initial: Props['initial'], interactive: boolean, dark: boolean) {
  const opts = interactive
    ? '{zoomControl:true,attributionControl:true,preferCanvas:true}'
    : '{zoomControl:false,attributionControl:true,preferCanvas:true,dragging:false,touchZoom:false,scrollWheelZoom:false,doubleClickZoom:false,boxZoom:false,keyboard:false,tap:false}';
  const ink = dark ? '#FFFFFF' : '#0B1B2B';
  return `<!doctype html><html><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<style>${LEAFLET_CSS}</style>
<style>
html,body,#map{margin:0;padding:0;width:100%;height:100%;background:${dark ? '#0E1823' : '#EEF5FB'}}
${dark ? '.leaflet-tile-pane{filter:invert(1) hue-rotate(180deg) brightness(.95) contrast(.9)}' : ''}
.kl-label{background:${dark ? 'rgba(22,35,47,.92)' : 'rgba(255,255,255,.92)'};color:${ink};border:none;border-radius:6px;
  box-shadow:0 1px 3px rgba(0,0,0,.25);font:700 12px system-ui,sans-serif;padding:2px 6px;pointer-events:none}
.kl-label:before{display:none}
.leaflet-control-attribution{font-size:10px}
</style>
<script>
function send(m){window.ReactNativeWebView&&window.ReactNativeWebView.postMessage(JSON.stringify(m))}
window.onerror=function(msg){send({type:'error',message:String(msg)})};
</script>
<script>${LEAFLET_JS}</script>
<script>${H3_JS}</script>
</head><body><div id="map"></div><script>
var map=L.map('map',${opts}).setView([${initial.lat},${initial.lon}],${initial.zoom});
map.attributionControl.setPrefix(false);
var tiles=L.tileLayer(${JSON.stringify(TILE_URL)},{maxZoom:18,attribution:${JSON.stringify(ATTRIBUTION)}}).addTo(map);
var loaded=0,failed=0,reported=false;
tiles.on('tileload',function(){loaded++});
tiles.on('tileerror',function(){failed++;if(!reported&&loaded===0&&failed>=4){reported=true;send({type:'tiles-error'})}});
var renderer=L.canvas({padding:.3});
var cells={}, cellLayer=L.layerGroup().addTo(map), overlay=L.layerGroup().addTo(map), placeLayer=L.layerGroup().addTo(map);
var NODATA={color:'#8A97A5',weight:.6,opacity:.6,fillColor:'#8A97A5',fillOpacity:.16};
var state={styles:{},selected:null};
function styleFor(id){
  var s=state.styles[id]||NODATA;
  if(id===state.selected){s=Object.assign({},s,{color:'${ink}',weight:3,opacity:1})}
  return s;
}
window.klSetGrid=function(ids){
  cellLayer.clearLayers();cells={};
  ids.forEach(function(id){
    var p=L.polygon(h3.cellToBoundary(id),Object.assign({renderer:renderer},styleFor(id)));  // [lat,lng] pairs
    p.on('click',function(){send({type:'cell',id:id})});
    p.addTo(cellLayer);cells[id]=p;
  });
};
window.klUpdate=function(d){
  var prevSel=state.selected;
  state.styles=d.styles||{};state.selected=d.selected||null;
  Object.keys(cells).forEach(function(id){cells[id].setStyle(styleFor(id))});
  if(state.selected&&cells[state.selected])cells[state.selected].bringToFront();
  overlay.clearLayers();
  (d.clusters||[]).forEach(function(c){
    L.circle([c.lat,c.lon],{radius:200,color:c.level==='danger'?'#7A120D':'#B86A00',weight:2,dashArray:'4 4',
      fillColor:c.level==='danger'?'#B3261E':'#F5B451',fillOpacity:.25}).bindPopup(c.text).addTo(overlay);
  });
  if(d.user){
    L.circleMarker([d.user.lat,d.user.lon],{radius:14,stroke:false,fillColor:'#1D5FD1',fillOpacity:.18,interactive:false}).addTo(overlay);
    L.circleMarker([d.user.lat,d.user.lon],{radius:7,color:'#FFFFFF',weight:3,fillColor:'#1D5FD1',fillOpacity:1}).addTo(overlay);
  }
  if(d.places){
    placeLayer.clearLayers();
    d.places.forEach(function(p){
      L.circleMarker([p.lat,p.lon],{radius:4,color:'${ink}',weight:1,fillColor:'${ink}',fillOpacity:1,interactive:false})
        .bindTooltip(p.name,{permanent:true,direction:'right',offset:[6,0],className:'kl-label'}).addTo(placeLayer);
    });
  }
  if(d.focus){map.setView([d.focus.lat,d.focus.lon],d.focus.zoom,{animate:true})}
};
send({type:'ready'});
</script></body></html>`;
}

export function IceMap({
  cells,
  statuses,
  places,
  selectedId,
  clusters = [],
  user,
  focus,
  initial,
  interactive = true,
  onSelectCell,
  style,
}: Props) {
  const c = usePalette();
  const dark = useIsDark();
  const ref = useRef<WebViewHandle>(null);
  const [ready, setReady] = useState(false);
  const [error, setError] = useState(false);
  const [tilesError, setTilesError] = useState(false);

  // initial/interactive/dark rebuild the page; data is pushed with klSetGrid/klUpdate
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const html = useMemo(() => buildHtml(initial, interactive, dark), [interactive, dark]);

  // geometry: once per page load or when the grid changes
  useEffect(() => {
    if (!ready) return;
    ref.current?.injectJavaScript(`window.klSetGrid(${JSON.stringify(cells.map((cell) => cell.id))});true;`);
  }, [ready, cells]);

  // statuses, selection and overlays: cheap, every refresh
  useEffect(() => {
    if (!ready) return;
    const styles: Record<string, object> = {};
    for (const [id, s] of Object.entries(statuses)) {
      if (s.level === 'nodata') continue;
      const lc = levelColors(c, s.level);
      styles[id] = { color: lc.stroke, weight: 1.5, opacity: 1, fillColor: lc.hex, fillOpacity: lc.opacity };
    }
    const payload = {
      styles,
      selected: selectedId ?? null,
      clusters,
      user: user ?? null,
      focus: focus ?? null,
      places: places?.map((p) => ({ name: p.name, lat: p.lat, lon: p.lon })),
    };
    ref.current?.injectJavaScript(`window.klUpdate(${JSON.stringify(payload)});true;`);
  }, [ready, cells, statuses, selectedId, clusters, user, focus, places, c]);

  return (
    <View style={[{ overflow: 'hidden' }, style]}>
      <MapWebView
        ref={ref}
        // the https origin makes the browser send a Referer with tile requests (OSM tile policy)
        source={{ html, baseUrl: 'https://krepkiy-led.app/' }}
        originWhitelist={['*']}
        javaScriptEnabled
        scrollEnabled={false}
        setSupportMultipleWindows={false}
        style={{ flex: 1, backgroundColor: 'transparent' }}
        onLoadStart={() => {
          setReady(false);
          setTilesError(false);
        }}
        onMessage={(e: WebViewMessageEvent) => {
          let m: { type: string; id?: string };
          try {
            m = JSON.parse(e.nativeEvent.data);
          } catch {
            return;
          }
          if (m.type === 'ready') {
            setReady(true);
            setError(false);
          } else if (m.type === 'cell' && m.id) onSelectCell?.(m.id);
          else if (m.type === 'tiles-error') setTilesError(true);
          else if (m.type === 'error') setError(true);
        }}
      />
      {!ready && !error && (
        <View style={[StyleSheet.absoluteFill, s.center]} pointerEvents="none">
          <ActivityIndicator color={c.accent} />
        </View>
      )}
      {error && (
        <View style={[StyleSheet.absoluteFill, s.placeholder, { backgroundColor: c.surface2 }]}>
          <Text style={[s.title, { color: c.ink }]}>Карта не запустилась</Text>
          <Text style={{ color: c.muted, fontSize: 13, textAlign: 'center' }}>Перезапустите приложение.</Text>
        </View>
      )}
      {tilesError && (
        <View style={[s.tilesBanner, { backgroundColor: c.surface }]} pointerEvents="none">
          <Text style={{ color: c.ink, fontSize: 12, fontWeight: '700', textAlign: 'center' }}>
            Подложка карты не загрузилась: нет интернета. Участки показаны без фона.
          </Text>
        </View>
      )}
    </View>
  );
}

const s = StyleSheet.create({
  center: { alignItems: 'center', justifyContent: 'center' },
  placeholder: { alignItems: 'center', justifyContent: 'center', padding: 24, gap: 8 },
  title: { fontSize: 16, fontWeight: '800' },
  tilesBanner: { position: 'absolute', left: 60, right: 60, top: '45%', borderRadius: 12, padding: 10 },
});
