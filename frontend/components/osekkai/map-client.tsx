'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

import EventMap from '@/app/osekkai/_components/event-map';
import styles from '@/app/osekkai/osekkai.module.css';
import { osekkaiApi } from '@/lib/osekkai/api';
import type { MapEventSummary, MapEventsResult, RankedOpportunity } from '@/lib/osekkai/types.generated';
import { friendlyApiError } from './api-client';

const EMPTY_COUNTS: MapEventsResult['counts'] = {
  totalInMesh: 0,
  inWard: 0,
  withCoordinates: 0,
  missingCoordinates: 0,
  returned: 0,
};

export default function MapClient() {
  const [events, setEvents] = useState<MapEventSummary[]>([]);
  const [counts, setCounts] = useState<MapEventsResult['counts']>(EMPTY_COUNTS);
  const [ranking, setRanking] = useState<RankedOpportunity[]>([]);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const loadVersion = useRef(0);

  const loadMapPages = useCallback(async () => {
    // Keep the mount Effect subscription-only; page state starts after the
    // first microtask and never delays the Google Maps canvas mount.
    await Promise.resolve();
    const version = ++loadVersion.current;
    setLoading(true);
    setLoadingMore(false);
    setError('');
    let offset: number | null = 0;
    let collected: MapEventSummary[] = [];
    let firstPage = true;

    try {
      while (offset !== null) {
        const page = await osekkaiApi.mapEvents(offset, 250);
        if (loadVersion.current !== version) return;
        collected = [...collected, ...page.events];
        setEvents(collected);
        setCounts(page.counts);
        offset = page.nextOffset;
        if (firstPage) {
          firstPage = false;
          setLoading(false);
        }
        setLoadingMore(offset !== null);
        if (offset !== null) await new Promise((resolve) => window.setTimeout(resolve, 0));
      }
    } catch (reason) {
      if (loadVersion.current === version) setError(friendlyApiError(reason));
    } finally {
      if (loadVersion.current === version) {
        setLoading(false);
        setLoadingMore(false);
      }
    }
  }, []);

  useEffect(() => {
    const mapLoadTimer = window.setTimeout(() => { void loadMapPages(); }, 0);
    void osekkaiApi.interventions().then((interventions) => {
      const latest = [...interventions.interventions].sort((left, right) => right.sequence - left.sequence)[0];
      setRanking((latest?.rankedOpportunities ?? []) as RankedOpportunity[]);
    }).catch(() => {
      // Recommendation history is enhancement-only and never blocks the map.
    });
    return () => {
      window.clearTimeout(mapLoadTimer);
      loadVersion.current += 1;
    };
  }, [loadMapPages]);

  const refresh = async () => {
    setSyncing(true);
    setError('');
    try {
      await osekkaiApi.syncSources(true);
      await loadMapPages();
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <div className={styles.mapPage}>
      <section className={styles.mapPageIntro}>
        <div>
          <p className={styles.eyebrow}>EVENT MAP</p>
          <h1>自分でもイベント、探せるで</h1>
          <p>最初に出てくる街は、今のところの目安なだけ。場所がちゃんと確認できたEventから、この地図にどんどん載せていくで。</p>
        </div>
        <button type="button" disabled={syncing} onClick={refresh}>{syncing ? 'Eventを更新中…' : 'Eventを更新'}</button>
      </section>
      {error ? <p className={styles.liveError} role="alert">Eventを読み込めませんでした。地図はそのまま使えます。{error}</p> : null}
      <EventMap events={events} ranking={ranking} counts={counts} loading={loading} loadingMore={loadingMore} />
    </div>
  );
}
