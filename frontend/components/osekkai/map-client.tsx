'use client';

import { useEffect, useMemo, useState } from 'react';

import EventMap from '@/app/osekkai/_components/event-map';
import LiveSourceStrip from '@/app/osekkai/_components/live-source-strip';
import styles from '@/app/osekkai/osekkai.module.css';
import { osekkaiApi } from '@/lib/osekkai/api';
import type { ConnectionEvidence, RankedOpportunity } from '@/lib/osekkai/types.generated';
import type { EventMeshResult, OpportunitiesResult, SourceStatusResult } from '@/lib/osekkai/types';
import { friendlyApiError } from './api-client';

function isConnectionEvidence(value: unknown): value is ConnectionEvidence {
  return Boolean(value) && typeof value === 'object' && value !== null &&
    'eventId' in value && 'connectionLevel' in value;
}

export default function MapClient() {
  const [mesh, setMesh] = useState<EventMeshResult | null>(null);
  const [opportunities, setOpportunities] = useState<OpportunitiesResult | null>(null);
  const [sources, setSources] = useState<SourceStatusResult | null>(null);
  const [ranking, setRanking] = useState<RankedOpportunity[]>([]);
  const [error, setError] = useState('');
  const [syncing, setSyncing] = useState(false);

  const load = async () => {
    const [eventMesh, currentOpportunities, sourceStatus, interventions] = await Promise.all([
      osekkaiApi.events(), osekkaiApi.opportunities(), osekkaiApi.sources(), osekkaiApi.interventions(),
    ]);
    setMesh(eventMesh); setOpportunities(currentOpportunities); setSources(sourceStatus);
    const latest = [...interventions.interventions].sort((left, right) => right.sequence - left.sequence)[0];
    setRanking((latest?.rankedOpportunities ?? []) as RankedOpportunity[]);
  };

  useEffect(() => {
    let active = true;
    void Promise.all([
      osekkaiApi.events(), osekkaiApi.opportunities(), osekkaiApi.sources(), osekkaiApi.interventions(),
    ]).then(([eventMesh, currentOpportunities, sourceStatus, interventions]) => {
      if (!active) return;
      setMesh(eventMesh); setOpportunities(currentOpportunities); setSources(sourceStatus);
      const latest = [...interventions.interventions].sort((left, right) => right.sequence - left.sequence)[0];
      setRanking((latest?.rankedOpportunities ?? []) as RankedOpportunity[]);
    }).catch((reason) => active && setError(friendlyApiError(reason)));
    return () => { active = false; };
  }, []);

  const refresh = async () => {
    setSyncing(true); setError('');
    try { await osekkaiApi.syncSources(true); await load(); }
    catch (reason) { setError(friendlyApiError(reason)); }
    finally { setSyncing(false); }
  };

  const evidence = useMemo(() => (mesh?.connectionEvidence ?? []).filter(isConnectionEvidence), [mesh]);

  return (
    <div className={styles.mapPage}>
      <section className={styles.mapPageIntro}>
        <div><p className={styles.eyebrow}>TOKYO EVENT EXPLORER</p><h1>おばさんに任せず、自分でも全部見てええ。</h1><p>推薦対象外、交流根拠未確認、満席・中止も隠しません。現在地は押した時だけ使い、保存しません。</p></div>
        <button type="button" disabled={syncing} onClick={refresh}>{syncing ? '最新Eventを更新中…' : 'OpenClawで最新に更新'}</button>
      </section>
      <LiveSourceStrip status={sources} />
      {error ? <p className={styles.liveError} role="alert">{error}</p> : null}
      {mesh ? <EventMap events={mesh.events} opportunities={opportunities?.opportunities ?? []} evidence={evidence} ranking={ranking} /> : <p className={styles.loadingPanel}>全Eventを読み込んでいます…</p>}
    </div>
  );
}
