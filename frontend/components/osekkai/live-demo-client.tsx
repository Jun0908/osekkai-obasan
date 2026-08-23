'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import RecommendationShortlist from '@/app/osekkai/_components/recommendation-shortlist';
import styles from '@/app/osekkai/osekkai.module.css';
import { osekkaiApi } from '@/lib/osekkai/api';
import type { DecisionResult, RankedOpportunity } from '@/lib/osekkai/types.generated';
import type { OpportunitiesResult } from '@/lib/osekkai/types';
import { friendlyApiError } from './api-client';
import DemoClient from './demo-client';

type Stage = 'idle' | 'sources' | 'calendar' | 'routes' | 'decision' | 'complete';

export default function LiveDemoClient() {
  const [mode, setMode] = useState<'demo' | 'live' | null>(null);
  const [opportunities, setOpportunities] = useState<OpportunitiesResult | null>(null);
  const [decision, setDecision] = useState<DecisionResult | null>(null);
  const [stage, setStage] = useState<Stage>('idle');
  const [error, setError] = useState('');
  const [calendarConnected, setCalendarConnected] = useState(false);
  const [busy, setBusy] = useState('');

  useEffect(() => {
    let active = true;
    void osekkaiApi.session().then(async (session) => {
      if (!active) return;
      setMode(session.dataMode);
      if (session.dataMode === 'live') {
        const currentOpportunities = await osekkaiApi.opportunities();
        if (active) {
          setOpportunities(currentOpportunities);
        }
      }
    }).catch((reason) => active && setError(friendlyApiError(reason)));
    return () => { active = false; };
  }, []);

  if (mode === null) return <p className={styles.loadingPanel} aria-live="polite">Demoを準備しています…</p>;
  if (mode === 'demo') return <DemoClient />;

  const runLiveDemo = async () => {
    setBusy('run');
    setError('');
    setDecision(null);
    try {
      setStage('sources');
      // Respect each provider's freshness window during the judge flow. A forced
      // refresh remains available on the Event Map, while repeated demo runs can
      // reuse the latest verified cache instead of waiting on every provider.
      await osekkaiApi.syncSources(false);

      setStage('calendar');
      const freebusy = await osekkaiApi.freebusy();
      setCalendarConnected(freebusy.source.type === 'google_freebusy');

      setStage('routes');
      const currentOpportunities = await osekkaiApi.opportunities();
      setOpportunities(currentOpportunities);

      setStage('decision');
      const response = await osekkaiApi.decide();
      setDecision(response.decision);
      setStage('complete');
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setBusy('');
    }
  };

  const recordAction = async (action: 'accepted' | 'declined' | 'pause_one_week' | 'revisit') => {
    if (!decision) return;
    setBusy(action);
    try {
      if (action === 'revisit') {
        await osekkaiApi.feedback(decision.episodeId, { distanceFeedback: 'push_more' });
      } else {
        await osekkaiApi.feedback(decision.episodeId, { actionResponse: action });
      }
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setBusy('');
    }
  };

  const ranking = (decision?.rankedOpportunities ?? []) as RankedOpportunity[];
  const cards = opportunities?.opportunities ?? [];
  const stages: Array<[Stage, string]> = [
    ['sources', '最新Event'], ['calendar', 'Calendar'], ['routes', 'Routes'], ['decision', '距離感Policy'], ['complete', '複数候補PUSH'],
  ];
  const activeIndex = stage === 'idle' ? -1 : stages.findIndex(([key]) => key === stage);

  return (
    <div className={styles.liveDemoPage}>
      <section className={styles.liveDemoHero}>
        <div>
          <p className={styles.eyebrow}>TOKYO LIVE CONNECTION DEMO</p>
          <h1><span>あんた、また家ばっかりやろ。</span><span>今日は“次も会える場所”を見つけたで。</span></h1>
          <p>
            OpenClawが東京都の最新Eventを更新し、交流の根拠を読み、あなたのCalendarとGoogle Routesで
            本当に行ける複数候補だけを押します。
          </p>
          <div className={styles.liveDemoActions}>
            <button className={styles.primaryButtonLarge} type="button" disabled={Boolean(busy)} onClick={runLiveDemo}>
              {busy === 'run' ? '東京を確認中…' : '最新データから提案をつくる'}
            </button>
            <Link className={styles.secondaryButtonLarge} href="/osekkai/map">地図で全部見る</Link>
          </div>
        </div>
        <aside className={styles.liveProofCard}>
          <span className={styles.obasanSeal}>お</span>
          <strong>検索結果やないで。</strong>
          <p>継続性・ひとり参加・会話の入口がSourceで確認できたものを、現実の空き時間と移動時間で絞っています。</p>
          <div><span>Calendar</span><b>{calendarConnected ? '実接続' : '接続確認前'}</b></div>
          <div><span>Routes</span><b>{cards.length ? '実測候補あり' : '同期待ち'}</b></div>
        </aside>
      </section>

      <ol className={styles.livePipeline} aria-label="Live判断の進行状況" aria-live="polite">
        {stages.map(([key, label], index) => (
          <li key={key} data-state={index < activeIndex || stage === 'complete' ? 'done' : index === activeIndex ? 'active' : 'waiting'}>
            <span>{index < activeIndex || stage === 'complete' ? '✓' : index + 1}</span>{label}
          </li>
        ))}
      </ol>

      {error ? (
        <div className={styles.liveError} role="alert">
          <strong>Live確認を完了できませんでした。</strong>
          <p>{error}</p>
          <a href="/api/osekkai/calendar/connect">Google Calendarを接続する</a>
        </div>
      ) : null}

      {decision?.notification ? (
        <section className={styles.pushMessage} aria-live="polite">
          <span className={styles.obasanSeal}>お</span>
          <div><small>いまのおっせかい</small><p>{decision.notification.text}</p></div>
        </section>
      ) : null}

      <section className={styles.liveRecommendations}>
        <div className={styles.sectionHeadingCompact}>
          <div><p className={styles.eyebrow}>RECOMMENDATION SET</p><h2>ひとつに決めつけへん。今のあなたに近い順。</h2></div>
          <span>{ranking.length} candidates</span>
        </div>
        <RecommendationShortlist opportunities={cards} ranking={ranking} onAction={recordAction} busy={busy} />
      </section>
    </div>
  );
}
