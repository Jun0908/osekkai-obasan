'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';

import styles from '@/app/osekkai/osekkai.module.css';
import { friendlyApiError, getOsekkaiSession, osekkaiRequest } from './api-client';
import {
  batteryBand,
  extractEpisodes,
  firstRecord,
  formatDateTime,
  isRecord,
  normalizeProfile,
  readNumber,
  readString,
  reasonLabel,
  type EpisodeView,
  type ProfileView,
} from './models';
import { ClassificationBadge, EmptyState, InlineNotice, LoadingBlock, ModeBadge, PageIntro } from './ui';

type MetricView = {
  key: string;
  label: string;
  value: number | null;
  classification: string;
  numerator?: number;
  denominator?: number;
  description: string;
  rate?: boolean;
};

const metricDefinitions: Record<string, { label: string; description: string; rate?: boolean }> = {
  justRightPushRate: { label: 'ちょうどいい率', description: '「ちょうどいい」÷ 距離評価の回答数', rate: true },
  just_right_push_rate: { label: 'ちょうどいい率', description: '「ちょうどいい」÷ 距離評価の回答数', rate: true },
  overreachRate: { label: '押しすぎ率', description: '押しすぎ・休止・通知停止があった一意なPUSH', rate: true },
  overreach_rate: { label: '押しすぎ率', description: '押しすぎ・休止・通知停止があった一意なPUSH', rate: true },
  underSupportRate: { label: 'もう少し押して率', description: '「もう少し押して」÷ 距離評価の回答数', rate: true },
  under_support_rate: { label: 'もう少し押して率', description: '「もう少し押して」÷ 距離評価の回答数', rate: true },
  acceptanceRate: { label: '提案承諾率', description: '「行ってみる」÷ 行動反応の対象PUSH', rate: true },
  acceptance_rate: { label: '提案承諾率', description: '「行ってみる」÷ 行動反応の対象PUSH', rate: true },
  attendanceRate: { label: '実参加率', description: '参加記録 ÷ 承諾した提案', rate: true },
  attendance_rate: { label: '実参加率', description: '参加記録 ÷ 承諾した提案', rate: true },
  revisitRate: { label: '再訪率', description: '再訪記録 ÷ 参加した場所', rate: true },
  revisit_rate: { label: '再訪率', description: '再訪記録 ÷ 参加した場所', rate: true },
  pushCount: { label: 'PUSH判断', description: '候補を実際に提案したEpisode数' },
  push_count: { label: 'PUSH判断', description: '候補を実際に提案したEpisode数' },
  noPushCount: { label: 'no-PUSH判断', description: '声をかけないと判断したEpisode数' },
  no_push_count: { label: 'no-PUSH判断', description: '声をかけないと判断したEpisode数' },
};

const legacyUnverifiedMetrics: MetricView[] = [
  { key: 'third-place', label: 'Third Place獲得率', value: null, classification: 'unverified', description: 'P1以降に定義・収集します。', rate: true },
  { key: 'role', label: 'Role獲得率', value: null, classification: 'unverified', description: '役割を元データなしに生成しません。', rate: true },
  { key: 'graduation', label: 'OSEKKAI Graduation', value: null, classification: 'unverified', description: '自発行動の長期観測が必要です。', rate: true },
  { key: 'ucla', label: 'UCLA-3変化', value: null, classification: 'unverified', description: '明示同意とbaseline / week 4 / week 8が必要です。' },
  { key: 'lpwa', label: 'Loneliness Point-Weeks Avoided', value: null, classification: 'unverified', description: '対照群なしに効果実績を作りません。' },
];

function normalizeMetrics(raw: unknown): MetricView[] {
  const root = firstRecord(raw);
  const source = root.metrics ?? root.items ?? raw;
  const toMetric = (key: string, value: unknown): MetricView => {
    const detail = firstRecord(value);
    const definition = metricDefinitions[key] ?? {
      label: readString(detail, 'label') ?? key,
      description: readString(detail, 'description', 'formula', 'note') ?? 'Episodeから再計算した指標です。',
    };
    const numeric = typeof value === 'number' ? value : readNumber(detail, 'value', 'rate');
    const rawValue = value === null || detail.value === null ? null : numeric ?? null;
    return {
      key: readString(detail, 'key', 'id', 'name') ?? key,
      label: readString(detail, 'label') ?? definition.label,
      value: rawValue,
      classification: readString(detail, 'classification', 'metricClassification') ?? 'demo',
      numerator: readNumber(detail, 'numerator'),
      denominator: readNumber(detail, 'denominator'),
      description: readString(detail, 'description', 'formula', 'note') ?? definition.description,
      rate: definition.rate ?? (rawValue !== null && rawValue >= 0 && rawValue <= 1),
    };
  };

  if (Array.isArray(source)) {
    return source.filter(isRecord).map((item, index) => {
      const key = readString(item, 'key', 'id', 'name') ?? `metric-${index}`;
      return toMetric(key, item);
    });
  }
  if (isRecord(source)) {
    const ignored = new Set(['generatedAt', 'dataMode', 'classification', 'schemaVersion']);
    return Object.entries(source)
      .filter(([key]) => !ignored.has(key))
      .map(([key, value]) => toMetric(key, value));
  }
  return [];
}

function metricValue(metric: MetricView) {
  if (metric.value === null) return '未計測';
  if (metric.rate) return `${Math.round(metric.value * 100)}%`;
  return new Intl.NumberFormat('ja-JP', { maximumFractionDigits: 2 }).format(metric.value);
}

async function fetchImpactSnapshot() {
  const [profileRaw, interventionRaw, metricsRaw, session] = await Promise.all([
    osekkaiRequest('/profile'),
    osekkaiRequest('/interventions'),
    osekkaiRequest('/metrics'),
    getOsekkaiSession(),
  ]);
  const metricsRoot = firstRecord(metricsRaw);
  const measuredMetrics = normalizeMetrics(metricsRoot.metrics ?? metricsRaw);
  const canonicalUnverified = metricsRoot.unverifiedMetrics;
  return {
    profile: normalizeProfile(profileRaw),
    episodes: extractEpisodes(interventionRaw),
    metrics: [
      ...measuredMetrics,
      ...(canonicalUnverified === undefined
        ? legacyUnverifiedMetrics
        : normalizeMetrics(canonicalUnverified)),
    ],
    mode: session.dataMode,
  };
}

function EpisodeCard({ episode, latest = false }: { episode: EpisodeView; latest?: boolean }) {
  return (
    <article className={styles.episodeCard}>
      <div className={styles.episodeMarker}>
        <span className={episode.shouldPush ? styles.logPush : styles.logNoPush} />
      </div>
      <div className={styles.episodeContent}>
        <div className={styles.episodeTopline}>
          <div>
            <span className={episode.shouldPush ? styles.pushBadge : styles.noPushBadge}>
              {episode.shouldPush ? 'PUSH' : 'NO PUSH'}
            </span>
            {latest ? <span className={styles.latestBadge}>最新</span> : null}
          </div>
          <time dateTime={episode.decidedAt}>{formatDateTime(episode.decidedAt)}</time>
        </div>
        <h3>{episode.selectedOpportunity?.title ?? (episode.shouldPush ? '提案を記録' : '声をかけない判断')}</h3>
        {episode.message ? <p>{episode.message}</p> : null}
        {episode.reasonCodes.length ? (
          <ul className={styles.reasonList}>
            {episode.reasonCodes.map((code) => (
              <li key={code}><code>{code}</code><span>{reasonLabel(code)}</span></li>
            ))}
          </ul>
        ) : <p className={styles.mutedPlaceholder}>理由コードはありません。</p>}
        <div className={styles.episodeOutcomes}>
          {episode.actionResponse ? <span>反応: {episode.actionResponse}</span> : null}
          {episode.distanceFeedback ? <span>距離評価: {episode.distanceFeedback}</span> : null}
          {episode.attendedAt ? <span>参加記録あり</span> : null}
          {episode.revisitedAt ? <span>再訪記録あり</span> : null}
          <ClassificationBadge classification={episode.classification ?? 'demo'} />
        </div>
      </div>
    </article>
  );
}

export default function ImpactClient() {
  const [profile, setProfile] = useState<ProfileView>();
  const [episodes, setEpisodes] = useState<EpisodeView[]>([]);
  const [metrics, setMetrics] = useState<MetricView[]>([]);
  const [mode, setMode] = useState<string>();
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const load = async (refresh = false) => {
    if (refresh) setRefreshing(true);
    else setLoading(true);
    setError('');
    try {
      const snapshot = await fetchImpactSnapshot();
      setProfile(snapshot.profile);
      setEpisodes(snapshot.episodes);
      setMetrics(snapshot.metrics);
      setMode(snapshot.mode);
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    let active = true;
    void fetchImpactSnapshot()
      .then((snapshot) => {
        if (!active) return;
        setProfile(snapshot.profile);
        setEpisodes(snapshot.episodes);
        setMetrics(snapshot.metrics);
        setMode(snapshot.mode);
      })
      .catch((reason: unknown) => {
        if (active) setError(friendlyApiError(reason));
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const allMetrics = metrics;
  const latest = episodes[0];
  const pushCount = episodes.filter((episode) => episode.shouldPush).length;
  const noPushCount = episodes.length - pushCount;
  const band = batteryBand(profile?.socialBattery ?? null);

  if (loading) {
    return <LoadingBlock label="判断履歴とKPIを再計算しています" />;
  }

  return (
    <>
      <PageIntro
        eyebrow="IMPACT & ACCOUNTABILITY"
        title="声をかけた理由も、かけなかった理由も。"
        aside={<ModeBadge mode={mode} />}
      >
        <p>KPIは保存済みの数字を足すのではなく、介入Episodeから毎回再計算しています。</p>
      </PageIntro>

      {error ? (
        <InlineNotice tone="error" title="最新データを読み込めませんでした">
          <p>{error}</p>
        </InlineNotice>
      ) : null}

      <div className={styles.impactToolbar}>
        <div className={styles.classificationLegend} aria-label="指標の分類">
          <ClassificationBadge classification="measured" />
          <ClassificationBadge classification="reference_estimate" />
          <ClassificationBadge classification="demo" />
          <ClassificationBadge classification="unverified" />
        </div>
        <button className={styles.secondaryButton} type="button" onClick={() => load(true)} disabled={refreshing}>
          {refreshing ? '更新中…' : '再計算して更新'}
        </button>
      </div>

      {!episodes.length && !error ? (
        <EmptyState title="まだ判断の記録がありません" href="/osekkai/demo" action="12段階デモを始める">
          <p>会話のあとに判断を実行すると、PUSHしなかった回もここへ残ります。</p>
        </EmptyState>
      ) : (
        <>
          <section className={styles.impactOverview}>
            <article className={styles.latestDecisionCard}>
              <div className={styles.panelHeader}>
                <div>
                  <p className={styles.eyebrow}>LATEST DECISION</p>
                  <h2>最新の判断</h2>
                </div>
                {latest ? (
                  <span className={latest.shouldPush ? styles.pushBadge : styles.noPushBadge}>
                    {latest.shouldPush ? 'PUSH' : 'NO PUSH'}
                  </span>
                ) : null}
              </div>
              {latest ? (
                <>
                  <p className={styles.latestMessage}>
                    {latest.message ?? (latest.shouldPush ? '条件に合う候補を1件だけ提案しました。' : '今回は声をかけませんでした。')}
                  </p>
                  <ul className={styles.reasonTiles}>
                    {latest.reasonCodes.map((code) => (
                      <li key={code}><code>{code}</code><span>{reasonLabel(code)}</span></li>
                    ))}
                  </ul>
                  <p className={styles.decisionTime}>判断: {formatDateTime(latest.decidedAt)}</p>
                </>
              ) : <p className={styles.mutedPlaceholder}>判断が記録されるとここに表示されます。</p>}
            </article>

            <aside className={styles.distanceSnapshot}>
              <p className={styles.eyebrow}>DISTANCE SNAPSHOT</p>
              <h2>いまの距離感</h2>
              <div className={styles.snapshotBattery}>
                <strong>{profile?.socialBattery ?? '—'}</strong>
                <span>Social Battery / 100</span>
              </div>
              <p>{band.label}</p>
              <dl>
                <div><dt>PUSH</dt><dd>{pushCount}回</dd></div>
                <div><dt>no-PUSH</dt><dd>{noPushCount}回</dd></div>
                <div><dt>人との関わり上限</dt><dd>{profile?.maxSocialIntensity ?? '—'} / 5</dd></div>
                <div><dt>連続拒否</dt><dd>{profile?.rejectionStreak ?? 0}回</dd></div>
              </dl>
              <Link href="/osekkai/settings">距離を設定する <span aria-hidden="true">→</span></Link>
            </aside>
          </section>

          <section className={styles.metricsSection} aria-labelledby="metric-heading">
            <div className={styles.sectionHeadingRow}>
              <div>
                <p className={styles.eyebrow}>KPI</p>
                <h2 id="metric-heading">わかっていること、まだわからないこと</h2>
                <p>分母が0の指標は0%にせず、「未計測」と表示します。</p>
              </div>
            </div>
            <div className={styles.metricGrid}>
              {allMetrics.map((metric) => (
                <article key={metric.key} className={metric.classification === 'unverified' ? styles.metricCardUnverified : styles.metricCard}>
                  <div className={styles.metricTopline}>
                    <ClassificationBadge classification={metric.classification} />
                    {typeof metric.denominator === 'number' ? <span>n={metric.denominator}</span> : null}
                  </div>
                  <strong className={styles.metricValue}>{metricValue(metric)}</strong>
                  <h3>{metric.label}</h3>
                  <p>{metric.description}</p>
                  {metric.value === null ? <small>必要な回答や観測がまだありません。</small> : null}
                </article>
              ))}
            </div>
          </section>

          <section className={styles.historySection} aria-labelledby="history-heading">
            <div className={styles.sectionHeadingRow}>
              <div>
                <p className={styles.eyebrow}>EPISODE LOG</p>
                <h2 id="history-heading">判断の履歴</h2>
                <p>PUSHしなかった判断も省かずに残します。</p>
              </div>
              <span>{episodes.length} Episode</span>
            </div>
            <div className={styles.episodeTimeline}>
              {episodes.map((episode, index) => <EpisodeCard key={episode.id} episode={episode} latest={index === 0} />)}
            </div>
          </section>
        </>
      )}

      <section className={styles.ethicsNote}>
        <span aria-hidden="true">i</span>
        <div>
          <strong>数字が示さないこと</strong>
          <p>
            この画面は、孤独や心の状態を診断しません。P0の値はデモシナリオです。
            対照群や長期観測がない効果指標は、値を作らず「未検証」と表示します。
          </p>
        </div>
      </section>
    </>
  );
}
