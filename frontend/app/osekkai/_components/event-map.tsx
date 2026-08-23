'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

import { osekkaiApi } from '@/lib/osekkai/api';
import type { ConnectionEvidence, EventRouteResult, LiveEvent, Opportunity, RankedOpportunity } from '@/lib/osekkai/types.generated';
import { friendlyApiError } from '@/components/osekkai/api-client';
import MapEventSheet from './map-event-sheet';
import styles from '../osekkai.module.css';

type Coordinates = { latitude: number; longitude: number };
type MapLike = {
  setCenter(value: { lat: number; lng: number }): void;
  setZoom(value: number): void;
  getZoom(): number | undefined;
  getBounds(): { contains(value: { lat: number; lng: number }): boolean } | undefined;
  addListener(name: string, callback: () => void): unknown;
};
type MarkerLike = { setMap(value: MapLike | null): void; addListener(name: string, callback: () => void): unknown };
type MapsApi = {
  Map: new (node: HTMLElement, options: Record<string, unknown>) => MapLike;
  Marker: new (options: Record<string, unknown>) => MarkerLike;
  Geocoder: new () => { geocode(request: Record<string, unknown>): Promise<{ results: Array<{ geometry: { location: { lat(): number; lng(): number } } }> }> };
  SymbolPath: { CIRCLE: unknown };
};

declare global {
  interface Window { google?: { maps: MapsApi } }
}

let mapsPromise: Promise<MapsApi> | null = null;
function loadMaps(key: string): Promise<MapsApi> {
  if (window.google?.maps) return Promise.resolve(window.google.maps);
  if (mapsPromise) return mapsPromise;
  mapsPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&language=ja&region=JP&loading=async`;
    script.async = true;
    script.onload = () => window.google?.maps ? resolve(window.google.maps) : reject(new Error('Maps APIを読み込めませんでした。'));
    script.onerror = () => reject(new Error('Maps APIを読み込めませんでした。'));
    document.head.appendChild(script);
  });
  return mapsPromise;
}

type Filter = 'all' | 'today' | 'weekend' | 'solo' | 'recurring' | 'networking' | 'meal' | 'recommended' | 'nearby';
const filters: Array<[Filter, string]> = [
  ['all', 'すべて'], ['today', '今日'], ['weekend', '今週末'], ['nearby', '30分以内'],
  ['solo', 'ひとり参加可'], ['recurring', '継続あり'], ['networking', 'Networking'],
  ['meal', 'みんなで食事'], ['recommended', 'おすすめのみ'],
];

function markerColor(event: LiveEvent, evidence: ConnectionEvidence | undefined, recommended: boolean) {
  if (event.status === 'canceled' || event.status === 'ended') return '#6b7280';
  if (event.status === 'sold_out' || event.registrationStatus === 'closed') return '#9e2f2f';
  if (recommended) return '#a64728';
  if (!evidence) return '#d4a647';
  if (evidence.connectionLevel < 2) return '#65736b';
  return '#285643';
}

export default function EventMap({
  events,
  opportunities,
  evidence,
  ranking,
}: {
  events: LiveEvent[];
  opportunities: Opportunity[];
  evidence: ConnectionEvidence[];
  ranking: RankedOpportunity[];
}) {
  const mapNode = useRef<HTMLDivElement>(null);
  const map = useRef<MapLike | null>(null);
  const markers = useRef<MarkerLike[]>([]);
  const maps = useRef<MapsApi | null>(null);
  const [positions, setPositions] = useState<Record<string, Coordinates>>({});
  const [selected, setSelected] = useState<LiveEvent | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [origin, setOrigin] = useState<Coordinates | null>(null);
  const [region, setRegion] = useState('');
  const [locationState, setLocationState] = useState('現在地は保存しません');
  const [mapError, setMapError] = useState('');
  const [routeError, setRouteError] = useState('');
  const [routeBusy, setRouteBusy] = useState(false);
  const [routes, setRoutes] = useState<Record<string, EventRouteResult>>({});
  const [mapRevision, setMapRevision] = useState(0);

  const evidenceById = useMemo(() => new Map(evidence.map((item) => [item.eventId, item])), [evidence]);
  const rankingByOpportunity = useMemo(() => new Map(ranking.map((item) => [item.opportunityId, item])), [ranking]);
  const opportunityByEvent = useMemo(() => new Map(opportunities.flatMap((item) => item.eventId ? [[item.eventId, item] as const] : [])), [opportunities]);
  const rankingByEvent = useMemo(() => new Map(Array.from(opportunityByEvent).flatMap(([eventId, opportunity]) => {
    const item = rankingByOpportunity.get(opportunity.id);
    return item ? [[eventId, item] as const] : [];
  })), [opportunityByEvent, rankingByOpportunity]);

  const filtered = useMemo(() => {
    const now = new Date();
    const today = now.toDateString();
    const weekendEnd = new Date(now); weekendEnd.setDate(now.getDate() + ((7 - now.getDay()) % 7) + 1);
    return events.filter((event) => {
      const fact = evidenceById.get(event.id);
      const start = new Date(event.startsAt);
      if (filter === 'today') return start.toDateString() === today;
      if (filter === 'weekend') return [0, 6].includes(start.getDay()) && start <= weekendEnd;
      if (filter === 'solo') return fact?.soloFriendly === 'yes';
      if (filter === 'recurring') return fact?.recurring === 'yes' || Boolean(event.seriesId);
      if (filter === 'networking') return event.categories.some((value) => /network|交流|コミュニティ/i.test(value));
      if (filter === 'meal') return fact?.sharedMeal === 'yes';
      if (filter === 'recommended') return rankingByEvent.has(event.id);
      if (filter === 'nearby') return (routes[event.id]?.minutes ?? opportunityByEvent.get(event.id)?.travelEstimate.minutes ?? 999) <= 30;
      return true;
    });
  }, [events, evidenceById, filter, opportunityByEvent, rankingByEvent, routes]);

  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!key || !mapNode.current) {
      setMapError('Google Maps API keyが未設定のため、同じ全Eventを一覧で表示しています。');
      return;
    }
    let cancelled = false;
    void loadMaps(key).then(async (api) => {
      if (cancelled || !mapNode.current) return;
      maps.current = api;
      map.current = new api.Map(mapNode.current, {
        center: { lat: 35.6812, lng: 139.7671 }, zoom: 11, mapTypeControl: false, streetViewControl: false,
      });
      map.current.addListener('idle', () => setMapRevision((value) => value + 1));
      const direct: Record<string, Coordinates> = {};
      events.forEach((event) => {
        if (event.latitude !== null && event.longitude !== null) direct[event.id] = { latitude: event.latitude, longitude: event.longitude };
      });
      setPositions(direct);
      const geocoder = new api.Geocoder();
      for (const event of events.filter((item) => !direct[item.id] && (item.address || item.venueName)).slice(0, 100)) {
        if (cancelled) break;
        try {
          const response = await geocoder.geocode({ address: event.address || event.venueName, region: 'JP' });
          const point = response.results[0]?.geometry.location;
          if (point) setPositions((current) => ({ ...current, [event.id]: { latitude: point.lat(), longitude: point.lng() } }));
        } catch { /* Unresolved events stay visible in the complete fallback list. */ }
      }
    }).catch((reason) => !cancelled && setMapError(friendlyApiError(reason)));
    return () => { cancelled = true; markers.current.forEach((marker) => marker.setMap(null)); };
  }, [events]);

  useEffect(() => {
    const api = maps.current;
    const activeMap = map.current;
    if (!api || !activeMap) return;
    markers.current.forEach((marker) => marker.setMap(null));
    const zoom = activeMap.getZoom() ?? 11;
    const grid = zoom < 11 ? 0.08 : zoom < 13 ? 0.03 : 0.008;
    const bounds = activeMap.getBounds();
    const groups = new Map<string, LiveEvent[]>();
    filtered.forEach((event) => {
      const point = positions[event.id];
      if (!point || (bounds && !bounds.contains({ lat: point.latitude, lng: point.longitude }))) return;
      const key = `${Math.round(point.latitude / grid)}:${Math.round(point.longitude / grid)}`;
      groups.set(key, [...(groups.get(key) ?? []), event]);
    });
    markers.current = Array.from(groups.values()).map((group) => {
      const points = group.map((event) => positions[event.id]);
      const center = { lat: points.reduce((sum, point) => sum + point.latitude, 0) / points.length, lng: points.reduce((sum, point) => sum + point.longitude, 0) / points.length };
      const single = group.length === 1 ? group[0] : null;
      const marker = new api.Marker({
        map: activeMap, position: center, title: single?.title ?? `${group.length}件のEvent`,
        label: group.length > 1 ? { text: String(group.length), color: '#fff', fontWeight: '700' } : undefined,
        icon: { path: api.SymbolPath.CIRCLE, scale: group.length > 1 ? 18 : 11, fillColor: single ? markerColor(single, evidenceById.get(single.id), rankingByEvent.has(single.id)) : '#20332b', fillOpacity: 0.94, strokeColor: '#fffdf8', strokeWeight: 3 },
      });
      marker.addListener('click', () => {
        if (single) setSelected(single);
        else { activeMap.setCenter(center); activeMap.setZoom(Math.min(17, zoom + 2)); }
      });
      return marker;
    });
  }, [evidenceById, filtered, mapRevision, positions, rankingByEvent]);

  const locate = () => {
    if (!navigator.geolocation) { setLocationState('このBrowserでは現在地を利用できません'); return; }
    setLocationState('現在地を確認中…');
    navigator.geolocation.getCurrentPosition((position) => {
      const value = { latitude: position.coords.latitude, longitude: position.coords.longitude };
      setOrigin(value); setLocationState('現在地を一時利用中（保存しません）');
      map.current?.setCenter({ lat: value.latitude, lng: value.longitude }); map.current?.setZoom(13);
    }, () => setLocationState('現在地を使わず、地域名で探せます'), { enableHighAccuracy: false, timeout: 8000, maximumAge: 60_000 });
  };

  const searchRegion = async () => {
    if (!region.trim() || !maps.current) return;
    try {
      const response = await new maps.current.Geocoder().geocode({ address: `${region} 東京都`, region: 'JP' });
      const point = response.results[0]?.geometry.location;
      if (!point) return;
      const value = { latitude: point.lat(), longitude: point.lng() };
      setOrigin(value); setLocationState(`${region}から検索中`); map.current?.setCenter({ lat: value.latitude, lng: value.longitude }); map.current?.setZoom(13);
    } catch { setLocationState('地域を見つけられませんでした'); }
  };

  const loadRoute = async () => {
    if (!selected || !origin) return;
    setRouteBusy(true); setRouteError('');
    try {
      const route = await osekkaiApi.eventRoute(selected.id, origin.latitude, origin.longitude);
      setRoutes((current) => ({ ...current, [selected.id]: route }));
    } catch (reason) { setRouteError(friendlyApiError(reason)); }
    finally { setRouteBusy(false); }
  };

  return (
    <div className={styles.eventMapLayout}>
      <div className={styles.mapToolbar}>
        <button type="button" onClick={locate}>◎ 現在地から探す</button>
        <div><input value={region} onChange={(event) => setRegion(event.target.value)} placeholder="駅名・地域名" aria-label="駅名または地域名" /><button type="button" onClick={searchRegion}>移動</button></div>
        <span aria-live="polite">{locationState}</span>
      </div>
      <div className={styles.mapFilters} aria-label="Event絞り込み">
        {filters.map(([value, label]) => <button type="button" data-active={filter === value} aria-pressed={filter === value} onClick={() => setFilter(value)} key={value}>{label}</button>)}
      </div>
      {mapError ? <p className={styles.mapFallbackNotice}>{mapError}</p> : null}
      <div className={styles.mapCanvas} ref={mapNode} aria-label="現在地周辺の全Event地図">
        {mapError ? <div className={styles.mapPlaceholder}><strong>Google Maps接続待ち</strong><span>Eventは欠落させず、下の一覧に全件表示しています。</span></div> : null}
      </div>
      <p className={styles.mapCount}>{filtered.length}件中、位置確認済み{filtered.filter((event) => positions[event.id]).length}件を表示。重複EventはSource統合済みです。</p>
      {routeError ? <p className={styles.mapRouteError} role="alert">{routeError}</p> : null}
      <section className={styles.mapFallbackList} aria-labelledby="all-events-heading">
        <div><h2 id="all-events-heading">取得した全Event</h2><span>{filtered.length}件</span></div>
        <ul>{filtered.map((event) => (
          <li key={event.id} data-status={event.status}>
            <button type="button" onClick={() => setSelected(event)}><strong>{event.title}</strong><span>{event.venueName || event.address || '場所未確認'} · {event.status}</span></button>
          </li>
        ))}</ul>
      </section>
      {selected ? <MapEventSheet event={selected} evidence={evidenceById.get(selected.id)} ranking={rankingByEvent.get(selected.id)} route={routes[selected.id]} routeBusy={routeBusy} canRoute={Boolean(origin)} onRoute={loadRoute} onClose={() => setSelected(null)} /> : null}
    </div>
  );
}
