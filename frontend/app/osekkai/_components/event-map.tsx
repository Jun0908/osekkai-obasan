'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { friendlyApiError } from '@/components/osekkai/api-client';
import { osekkaiApi } from '@/lib/osekkai/api';
import type { CommunityDirectoryResult, CommunityFacilityDetail, CommunityFacilitySummary } from '@/lib/osekkai/community-directory-types';
import type { EventRouteResult, MapEventSummary, MapEventsResult, RankedOpportunity } from '@/lib/osekkai/types.generated';
import CommunityDirectorySheet from './community-directory-sheet';
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
  SymbolPath: { CIRCLE: unknown };
};

declare global {
  interface Window { google?: { maps: MapsApi } }
}

const KOJIMACHI = { latitude: 35.6840, longitude: 139.7373 };
const INITIAL_ZOOM = 14;
const WARD_ZOOM = 13;
const ALL_WARDS_ZOOM = 10;
const ALL_WARDS_VALUE = '__all__';
const DEFAULT_WARD = '千代田区';
const INITIAL_LIST_LIMIT = 40;

let mapsPromise: Promise<MapsApi> | null = null;
function isConstructor(value: unknown): value is new (...args: never[]) => unknown {
  if (typeof value !== 'function') return false;
  try {
    Reflect.construct(String, [], value);
    return true;
  } catch {
    return false;
  }
}

async function readyMaps(api: MapsApi): Promise<MapsApi> {
  for (let attempt = 0; attempt < 200; attempt += 1) {
    if (isConstructor(api.Map) && isConstructor(api.Marker) && api.SymbolPath) return api;
    await new Promise((resolve) => window.setTimeout(resolve, 25));
  }
  throw new Error('Maps APIを読み込めませんでした。');
}

function loadMaps(key: string): Promise<MapsApi> {
  if (window.google?.maps) return readyMaps(window.google.maps);
  if (mapsPromise) return mapsPromise;
  mapsPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&v=weekly&language=ja&region=JP&libraries=marker&loading=async`;
    script.async = true;
    script.onload = () => {
      const api = window.google?.maps;
      if (!api) { reject(new Error('Maps APIを読み込めませんでした。')); return; }
      void readyMaps(api).then(resolve, reject);
    };
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

function markerColor(event: MapEventSummary, recommended: boolean) {
  if (event.status === 'canceled' || event.status === 'ended') return '#6b7280';
  if (event.status === 'sold_out' || event.registrationStatus === 'closed') return '#9e2f2f';
  if (recommended) return '#a64728';
  if (!event.connectionEvidence) return '#d4a647';
  if (event.connectionEvidence.connectionLevel < 2) return '#65736b';
  return '#285643';
}

export default function EventMap({ events, ranking, counts, loading, loadingMore }: {
  events: MapEventSummary[];
  ranking: RankedOpportunity[];
  counts: MapEventsResult['counts'];
  loading: boolean;
  loadingMore: boolean;
}) {
  const mapNode = useRef<HTMLDivElement>(null);
  const map = useRef<MapLike | null>(null);
  const markers = useRef<MarkerLike[]>([]);
  const communityMarkers = useRef<MarkerLike[]>([]);
  const [selected, setSelected] = useState<MapEventSummary | null>(null);
  const [communities, setCommunities] = useState<CommunityDirectoryResult | null>(null);
  const [showCommunities, setShowCommunities] = useState(true);
  const [selectedFacility, setSelectedFacility] = useState<CommunityFacilityDetail | null>(null);
  const [facilityLoading, setFacilityLoading] = useState(false);
  const [facilityError, setFacilityError] = useState('');
  const [wardChoice, setWardChoice] = useState(DEFAULT_WARD);
  const [excludeAgeUnrelated, setExcludeAgeUnrelated] = useState(false);
  const [onlySports, setOnlySports] = useState(false);
  const [filter, setFilter] = useState<Filter>('all');
  const [origin, setOrigin] = useState<Coordinates | null>(null);
  const [locationState, setLocationState] = useState('地図は麹町中心・現在地は保存しません');
  const [mapError, setMapError] = useState('');
  const [routeError, setRouteError] = useState('');
  const [routeBusy, setRouteBusy] = useState(false);
  const [routes, setRoutes] = useState<Record<string, EventRouteResult>>({});
  const [mapRevision, setMapRevision] = useState(0);
  const [listLimit, setListLimit] = useState(INITIAL_LIST_LIMIT);

  const rankingByOpportunity = useMemo(() => new Map(ranking.map((item) => [item.opportunityId, item])), [ranking]);
  const rankingByEvent = useMemo(() => new Map(events.flatMap((event) => {
    const item = event.opportunityId ? rankingByOpportunity.get(event.opportunityId) : undefined;
    return item ? [[event.id, item] as const] : [];
  })), [events, rankingByOpportunity]);

  const filtered = useMemo(() => {
    const now = new Date();
    const today = now.toDateString();
    const weekendEnd = new Date(now); weekendEnd.setDate(now.getDate() + ((7 - now.getDay()) % 7) + 1);
    return events.filter((event) => {
      const fact = event.connectionEvidence;
      const start = new Date(event.startsAt);
      if (filter === 'today') return start.toDateString() === today;
      if (filter === 'weekend') return [0, 6].includes(start.getDay()) && start <= weekendEnd;
      if (filter === 'solo') return fact?.soloFriendly === 'yes';
      if (filter === 'recurring') return fact?.recurring === 'yes' || Boolean(event.seriesId);
      if (filter === 'networking') return event.categories.some((value) => /network|交流|コミュニティ/i.test(value));
      if (filter === 'meal') return fact?.sharedMeal === 'yes';
      if (filter === 'recommended') return rankingByEvent.has(event.id);
      if (filter === 'nearby') return (routes[event.id]?.minutes ?? event.travelMinutes ?? 999) <= 30;
      return true;
    });
  }, [events, filter, rankingByEvent, routes]);

  const wardOptions = useMemo(() => {
    if (!communities) return [];
    const byWard = new Map<string, CommunityFacilitySummary>();
    for (const facility of communities.facilities) {
      const current = byWard.get(facility.ward);
      if (!current || facility.locationKind === 'ward_office') byWard.set(facility.ward, facility);
    }
    return Array.from(byWard.values()).sort((left, right) => left.ward.localeCompare(right.ward, 'ja'));
  }, [communities]);

  useEffect(() => {
    const key = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY;
    if (!key || !mapNode.current) {
      setMapError('Google Maps API keyが未設定のため、Eventを一覧で表示しています。');
      return;
    }
    let cancelled = false;
    void loadMaps(key).then((api) => {
      if (cancelled || !mapNode.current) return;
      map.current = new api.Map(mapNode.current, {
        center: { lat: KOJIMACHI.latitude, lng: KOJIMACHI.longitude },
        zoom: INITIAL_ZOOM,
        mapTypeControl: false,
        streetViewControl: false,
      });
      map.current.addListener('idle', () => setMapRevision((value) => value + 1));
    }).catch((reason) => !cancelled && setMapError(friendlyApiError(reason)));
    return () => {
      cancelled = true;
      markers.current.forEach((marker) => marker.setMap(null));
    };
  }, []);

  const communityFilterParams = useMemo(() => {
    const params = new URLSearchParams();
    if (excludeAgeUnrelated) params.set('excludeAgeUnrelated', '1');
    if (onlySports) params.set('onlySports', '1');
    return params;
  }, [excludeAgeUnrelated, onlySports]);

  useEffect(() => {
    let cancelled = false;
    const query = communityFilterParams.toString();
    void fetch(`/api/osekkai/community-directory${query ? `?${query}` : ''}`)
      .then((response) => (response.ok ? (response.json() as Promise<CommunityDirectoryResult>) : null))
      .then((data) => { if (!cancelled && data) setCommunities(data); })
      .catch(() => {
        // Community directory pins are enhancement-only and never block the Event map.
      });
    return () => { cancelled = true; };
  }, [communityFilterParams]);

  const openFacility = useCallback((facility: CommunityFacilitySummary) => {
    setSelected(null);
    setSelectedFacility(null);
    setFacilityError('');
    setFacilityLoading(true);
    const params = new URLSearchParams(communityFilterParams);
    params.set('key', facility.key);
    void fetch(`/api/osekkai/community-directory?${params.toString()}`)
      .then((response) => (response.ok ? (response.json() as Promise<CommunityFacilityDetail>) : null))
      .then((detail) => {
        if (detail) setSelectedFacility(detail);
        else setFacilityError('この拠点の一覧を取得できませんでした。');
      })
      .catch(() => setFacilityError('この拠点の一覧を取得できませんでした。'))
      .finally(() => setFacilityLoading(false));
  }, [communityFilterParams]);

  const visibleFacilities = useMemo(() => {
    if (!communities) return [];
    if (wardChoice === ALL_WARDS_VALUE) return communities.facilities;
    return communities.facilities.filter((facility) => facility.ward === wardChoice);
  }, [communities, wardChoice]);
  const visibleCommunityCount = useMemo(
    () => visibleFacilities.reduce((sum, facility) => sum + facility.count, 0),
    [visibleFacilities],
  );

  useEffect(() => {
    const api = window.google?.maps;
    const activeMap = map.current;
    if (!api || !activeMap) return;
    communityMarkers.current.forEach((marker) => marker.setMap(null));
    if (!showCommunities) { communityMarkers.current = []; return; }
    communityMarkers.current = visibleFacilities.map((facility) => {
      const marker = new api.Marker({
        map: activeMap,
        position: { lat: facility.latitude, lng: facility.longitude },
        title: `${facility.ward} ${facility.name} · 地域コミュニティ${facility.count}件（Open Data・目安地点）`,
        label: { text: String(facility.count), color: '#fff', fontWeight: '700' },
      });
      marker.addListener('click', () => openFacility(facility));
      return marker;
    });
  }, [visibleFacilities, showCommunities, mapRevision, openFacility]);

  useEffect(() => {
    const api = window.google?.maps;
    const activeMap = map.current;
    if (!api || !activeMap) return;
    markers.current.forEach((marker) => marker.setMap(null));
    const zoom = activeMap.getZoom() ?? INITIAL_ZOOM;
    const grid = zoom < 11 ? 0.08 : zoom < 13 ? 0.03 : 0.008;
    const bounds = activeMap.getBounds();
    const groups = new Map<string, MapEventSummary[]>();
    filtered.forEach((event) => {
      if (bounds && !bounds.contains({ lat: event.latitude, lng: event.longitude })) return;
      const key = `${Math.round(event.latitude / grid)}:${Math.round(event.longitude / grid)}`;
      groups.set(key, [...(groups.get(key) ?? []), event]);
    });
    markers.current = Array.from(groups.values()).map((group) => {
      const center = {
        lat: group.reduce((sum, event) => sum + event.latitude, 0) / group.length,
        lng: group.reduce((sum, event) => sum + event.longitude, 0) / group.length,
      };
      const single = group.length === 1 ? group[0] : null;
      const marker = new api.Marker({
        map: activeMap,
        position: center,
        title: single?.title ?? `${group.length}件のEvent`,
        label: group.length > 1 ? { text: String(group.length), color: '#fff', fontWeight: '700' } : undefined,
        icon: {
          path: api.SymbolPath.CIRCLE,
          scale: group.length > 1 ? 18 : 11,
          fillColor: single ? markerColor(single, rankingByEvent.has(single.id)) : '#20332b',
          fillOpacity: 0.94,
          strokeColor: '#fffdf8',
          strokeWeight: 3,
        },
      });
      marker.addListener('click', () => {
        setSelectedFacility(null);
        if (single) setSelected(single);
        else { activeMap.setCenter(center); activeMap.setZoom(Math.min(17, zoom + 2)); }
      });
      return marker;
    });
  }, [filtered, mapRevision, rankingByEvent]);

  const locate = () => {
    if (!navigator.geolocation) { setLocationState('このBrowserでは現在地を利用できません'); return; }
    setLocationState('現在地を確認中…');
    navigator.geolocation.getCurrentPosition((position) => {
      setOrigin({ latitude: position.coords.latitude, longitude: position.coords.longitude });
      setLocationState('現在地を移動時間だけに利用中（保存しません）');
    }, () => setLocationState('現在地を使わず、地図のEventを見られます'), { enableHighAccuracy: false, timeout: 8000, maximumAge: 60_000 });
  };

  const resetToKojimachi = () => {
    setWardChoice(DEFAULT_WARD);
    map.current?.setCenter({ lat: KOJIMACHI.latitude, lng: KOJIMACHI.longitude });
    map.current?.setZoom(INITIAL_ZOOM);
  };

  const jumpToWard = (ward: string) => {
    setWardChoice(ward);
    if (ward === ALL_WARDS_VALUE) {
      map.current?.setCenter({ lat: KOJIMACHI.latitude, lng: KOJIMACHI.longitude });
      map.current?.setZoom(ALL_WARDS_ZOOM);
      return;
    }
    if (ward === DEFAULT_WARD) {
      map.current?.setCenter({ lat: KOJIMACHI.latitude, lng: KOJIMACHI.longitude });
      map.current?.setZoom(INITIAL_ZOOM);
      return;
    }
    const target = wardOptions.find((facility) => facility.ward === ward);
    if (!target || !map.current) return;
    map.current.setCenter({ lat: target.latitude, lng: target.longitude });
    map.current.setZoom(WARD_ZOOM);
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

  const visibleList = filtered.slice(0, listLimit);

  return (
    <div className={styles.eventMapLayout}>
      <div className={styles.mapToolbar}>
        <button type="button" onClick={locate}>◎ 現在地を移動時間に使う</button>
        <button type="button" onClick={resetToKojimachi}>麹町へ戻る</button>
        <button type="button" data-active={showCommunities} onClick={() => setShowCommunities((value) => !value)}>
          ⌂ 地域コミュニティ{showCommunities ? 'を隠す' : 'を表示'}
        </button>
        <button
          type="button"
          data-active={excludeAgeUnrelated}
          aria-pressed={excludeAgeUnrelated}
          onClick={() => setExcludeAgeUnrelated((value) => !value)}
          title="町会・自治会・シニア向けクラブなどを除いて表示します"
        >
          20〜30代向けのみ
        </button>
        <button
          type="button"
          data-active={onlySports}
          aria-pressed={onlySports}
          onClick={() => setOnlySports((value) => !value)}
          title="スポーツ・運動系のコミュニティのみ表示します"
        >
          スポーツ・運動系のみ
        </button>
        <select aria-label="表示する区を選ぶ" value={wardChoice} onChange={(event) => jumpToWard(event.target.value)}>
          {wardOptions.map((option) => <option key={option.ward} value={option.ward}>{option.ward}</option>)}
          <option value={ALL_WARDS_VALUE}>全23区をまとめて表示</option>
        </select>
        <span aria-live="polite">{locationState}</span>
      </div>
      <div className={styles.mapFilters} aria-label="Event絞り込み">
        {filters.map(([value, label]) => <button type="button" data-active={filter === value} aria-pressed={filter === value} onClick={() => { setFilter(value); setListLimit(INITIAL_LIST_LIMIT); }} key={value}>{label}</button>)}
      </div>
      <div className={styles.mapCanvasWrap}>
        <div className={styles.mapCanvas} ref={mapNode} aria-label="Event地図（区を選んで移動できます）" />
        {loading ? <div className={styles.mapLoadingBadge}>地図を先に表示中 · Eventを取得しています</div> : null}
        {loadingMore ? <div className={styles.mapLoadingBadge}>追加Eventを地図へ載せています</div> : null}
        {facilityLoading ? <div className={styles.mapLoadingBadge}>拠点のコミュニティ一覧を取得中…</div> : null}
        {mapError ? <div className={styles.mapPlaceholder}><strong>Google Maps接続待ち</strong><span>{mapError}</span></div> : null}
      </div>
      <p className={styles.mapCount}>
        全{counts.totalInMesh.toLocaleString()}件から千代田区{counts.inWard.toLocaleString()}件に限定。座標確認済み{events.length.toLocaleString()}件を表示{counts.missingCoordinates > 0 ? `、住所のみ${counts.missingCoordinates.toLocaleString()}件は地図描画待ち` : ''}。
      </p>
      {communities ? (
        <p className={styles.mapCount}>
          {wardChoice === ALL_WARDS_VALUE
            ? `東京23区の地域コミュニティ${communities.counts.total.toLocaleString()}件を${communities.facilities.length.toLocaleString()}地点に表示。地域名・町丁目の活動区域${communities.counts.withAreaLocation.toLocaleString()}件を区役所から分散（Open Data・開催日時未確認）。`
            : `${wardChoice}の地域コミュニティ${visibleCommunityCount.toLocaleString()}件を${visibleFacilities.length.toLocaleString()}地点で表示中（東京23区全体では${communities.counts.total.toLocaleString()}件）。他の区は上のセレクトから選べます。`}
          {excludeAgeUnrelated ? '町会・自治会・シニア向けクラブなどを除いています。' : ''}
          {onlySports ? 'スポーツ・運動系のみに絞っています。' : ''}
        </p>
      ) : null}
      {facilityError ? <p className={styles.mapRouteError} role="alert">{facilityError}</p> : null}
      {routeError ? <p className={styles.mapRouteError} role="alert">{routeError}</p> : null}
      <section className={styles.mapFallbackList} aria-labelledby="all-events-heading">
        <div><h2 id="all-events-heading">Event一覧</h2><span>{filtered.length}件</span></div>
        {visibleList.length > 0 ? <ul>{visibleList.map((event) => (
          <li key={event.id} data-status={event.status}>
            <button type="button" onClick={() => { setSelectedFacility(null); setSelected(event); }}><strong>{event.title}</strong><span>{event.venueName || event.address || '場所未確認'} · {event.status}</span></button>
          </li>
        ))}</ul> : <p className={styles.mapEmptyState}>{loading ? 'Eventは地図の後から読み込まれます。' : 'この条件のEventはありません。'}</p>}
        {visibleList.length < filtered.length ? <button className={styles.mapListMore} type="button" onClick={() => setListLimit((value) => value + INITIAL_LIST_LIMIT)}>続きを表示</button> : null}
      </section>
      {selected ? <MapEventSheet event={selected} evidence={selected.connectionEvidence ?? undefined} ranking={rankingByEvent.get(selected.id)} route={routes[selected.id]} routeBusy={routeBusy} canRoute={Boolean(origin)} onRoute={loadRoute} onClose={() => setSelected(null)} /> : null}
      {selectedFacility && communities ? (
        <CommunityDirectorySheet facility={selectedFacility} note={communities.dataSource.note} onClose={() => setSelectedFacility(null)} />
      ) : null}
    </div>
  );
}
