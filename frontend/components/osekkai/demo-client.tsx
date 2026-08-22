'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';

import styles from '@/app/osekkai/osekkai.module.css';
import {
  friendlyApiError,
  getOsekkaiSession,
  newIdempotencyKey,
  osekkaiRequest,
  type JsonObject,
} from './api-client';
import {
  batteryBand,
  extractOpportunities,
  firstRecord,
  formatDateTime,
  isRecord,
  normalizeEpisode,
  normalizeOpportunity,
  normalizeProfile,
  objectArray,
  readNumber,
  readString,
  reasonLabel,
  type EpisodeView,
  type OpportunityView,
  type ProfileView,
} from './models';
import { ClassificationBadge, InlineNotice, ModeBadge, PageIntro } from './ui';

type FreeWindowView = {
  start?: string;
  end?: string;
  durationMinutes?: number;
};

type DemoLog = {
  id: string;
  title: string;
  detail: string;
  tone?: 'push' | 'no-push' | 'plain';
};

const steps = [
  { title: '疲れた気持ちを話す', detail: '「今週疲れた。何もしたくない」を送ります。', action: '会話を送る' },
  { title: 'Profileの変化を見る', detail: 'Social Batteryが低めになったことを確認します。', action: 'Profileを確認' },
  { title: 'いまはPUSHしない', detail: '本人の「何もしたくない」を最優先します。', action: '判断を実行' },
  { title: '後日の気持ちを話す', detail: '「少し外に出たいが、話したくない」を送ります。', action: '次の会話を送る' },
  { title: '4時間の空きを確認', detail: '予定の中身を含まない合成Free/Busyです。', action: '空き時間を読む' },
  { title: '公開データ候補を確認', detail: '過去のsource snapshotを読み、現在情報と区別します。', action: '候補を読む' },
  { title: '1件だけ提案', detail: '移動・予算・Social Intensityを満たす1件を選びます。', action: '判断を実行' },
  { title: '「行ってみる」', detail: '提案への行動反応を記録します。', action: '行ってみる' },
  { title: '「ちょうどいい」', detail: '声かけの距離を評価します。', action: 'ちょうどいい' },
  { title: '実参加をシミュレーション', detail: 'デモEpisodeに参加時刻を記録します。', action: '参加を記録' },
  { title: '再訪をシミュレーション', detail: '同じ場所へもう一度行ったことを記録します。', action: '再訪を記録' },
  { title: 'Impactでふりかえる', detail: 'PUSH/no-PUSH理由と分類付きKPIを確認します。', action: 'KPIを更新' },
] as const;

function normalizeFreeWindow(raw: unknown): FreeWindowView | undefined {
  const root = firstRecord(raw);
  const list = objectArray(root.freeWindows ?? root.windows ?? raw);
  const item = list[0];
  if (!item) return undefined;
  return {
    start: readString(item, 'start', 'startsAt'),
    end: readString(item, 'end', 'endsAt'),
    durationMinutes: readNumber(item, 'durationMinutes', 'duration'),
  };
}

function decisionFrom(raw: unknown) {
  if (!isRecord(raw)) return undefined;
  const direct = normalizeEpisode(raw);
  if (!direct) return undefined;
  const selected = direct.selectedOpportunity
    ?? (isRecord(raw.decision) ? normalizeEpisode(raw.decision)?.selectedOpportunity : undefined);
  return { ...direct, selectedOpportunity: selected };
}

function episodeIdFrom(raw: unknown, episode?: EpisodeView) {
  const root = firstRecord(raw);
  return episode?.id !== 'unknown-episode'
    ? episode?.id
    : readString(root, 'episodeId', 'id');
}

export default function DemoClient() {
  const [completed, setCompleted] = useState(0);
  const [initializing, setInitializing] = useState(true);
  const [demoReady, setDemoReady] = useState(false);
  const [running, setRunning] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [resetConfirmText, setResetConfirmText] = useState('');
  const [mode, setMode] = useState<string>('demo');
  const [profile, setProfile] = useState<ProfileView>();
  const [freeWindow, setFreeWindow] = useState<FreeWindowView>();
  const [opportunities, setOpportunities] = useState<OpportunityView[]>([]);
  const [firstDecision, setFirstDecision] = useState<EpisodeView>();
  const [decision, setDecision] = useState<EpisodeView>();
  const [episodeId, setEpisodeId] = useState('');
  const [metricsReady, setMetricsReady] = useState(false);
  const [logs, setLogs] = useState<DemoLog[]>([]);
  const [error, setError] = useState('');
  const [reactionBusy, setReactionBusy] = useState('');
  const initializationPromiseRef = useRef<Promise<string> | null>(null);
  const initializationKeyRef = useRef<string | null>(null);
  if (initializationKeyRef.current === null) {
    initializationKeyRef.current = newIdempotencyKey('demo-seed');
  }

  useEffect(() => {
    let active = true;
    if (!initializationPromiseRef.current) {
      initializationPromiseRef.current = (async () => {
        const session = await getOsekkaiSession();
        if (session.dataMode === 'demo') {
          await osekkaiRequest('/demo/seed', {
            method: 'POST',
            mutation: true,
            body: { idempotencyKey: initializationKeyRef.current },
          });
        }
        return session.dataMode;
      })();
    }

    void initializationPromiseRef.current
      .then((dataMode) => {
        if (!active) return;
        setMode(dataMode);
        setDemoReady(true);
      })
      .catch((reason) => {
        if (!active) return;
        setMode('demo');
        setError(friendlyApiError(reason));
        setDemoReady(false);
      })
      .finally(() => {
        if (active) setInitializing(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const addLog = (title: string, detail: string, tone: DemoLog['tone'] = 'plain') => {
    setLogs((current) => [
      { id: newIdempotencyKey('log'), title, detail, tone },
      ...current,
    ]);
  };

  const resetDemo = async () => {
    if (resetConfirmText !== 'リセット') return;
    setResetting(true);
    setError('');
    try {
      await osekkaiRequest('/demo/reset', {
        method: 'POST',
        mutation: true,
        body: { idempotencyKey: newIdempotencyKey('demo-reset') },
      });
      setCompleted(0);
      setProfile(undefined);
      setFreeWindow(undefined);
      setOpportunities([]);
      setFirstDecision(undefined);
      setDecision(undefined);
      setEpisodeId('');
      setMetricsReady(false);
      setLogs([]);
      setDemoReady(true);
      setResetConfirmOpen(false);
      setResetConfirmText('');
      addLog('デモをリセット', '同じ固定時計とfixtureから始めます。');
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setResetting(false);
    }
  };

  const chat = async (message: string) => osekkaiRequest<JsonObject>('/chat', {
    method: 'POST',
    mutation: true,
    body: { message, remember: true, idempotencyKey: newIdempotencyKey('demo-chat') },
  });

  const decide = async () => osekkaiRequest<JsonObject>('/decide', {
    method: 'POST',
    mutation: true,
    body: { idempotencyKey: newIdempotencyKey('demo-decide') },
  });

  const sendFeedback = async (kind: 'action' | 'distance', value: string) => {
    if (!episodeId) throw new Error('対象の提案Episodeが見つかりません。ステップ7から再実行してください。');
    return osekkaiRequest<JsonObject>('/feedback', {
      method: 'POST',
      mutation: true,
      body: {
        episodeId,
        ...(kind === 'action' ? { actionResponse: value } : { distanceFeedback: value }),
        idempotencyKey: newIdempotencyKey(`demo-${value}`),
      },
    });
  };

  const transition = async (event: 'attended' | 'revisited') => {
    if (!episodeId) throw new Error('対象の提案Episodeが見つかりません。ステップ7から再実行してください。');
    return osekkaiRequest<JsonObject>('/interventions', {
      method: 'POST',
      mutation: true,
      body: {
        episodeId,
        event,
        transition: event,
        idempotencyKey: newIdempotencyKey(`demo-${event}`),
      },
    });
  };

  const runCurrentStep = async () => {
    if (!demoReady || running || completed >= steps.length) return;
    setRunning(true);
    setError('');
    const next = completed + 1;
    try {
      if (next === 1) {
        const raw = await chat('今週疲れた。何もしたくない');
        const result = firstRecord(raw.chatResult, raw.result, raw);
        addLog('会話', readString(result, 'reply', 'message') ?? '疲れた気持ちを受け取りました。');
      } else if (next === 2) {
        const raw = await osekkaiRequest('/profile');
        const nextProfile = normalizeProfile(raw);
        setProfile(nextProfile);
        addLog('Profile更新', `Social Battery: ${nextProfile.socialBattery ?? '未観測'}`);
      } else if (next === 3) {
        const raw = await decide();
        const nextDecision = decisionFrom(raw);
        setFirstDecision(nextDecision);
        addLog(
          'NO PUSH',
          nextDecision?.reasonCodes.map(reasonLabel).join('・') || '今回は提案しない判断です。',
          'no-push',
        );
      } else if (next === 4) {
        const raw = await chat('少し外に出たいが、話したくない');
        const result = firstRecord(raw.chatResult, raw.result, raw);
        addLog('後日の会話', readString(result, 'reply', 'message') ?? '外に出たい気持ちを受け取りました。');
        const profileRaw = await osekkaiRequest('/profile');
        setProfile(normalizeProfile(profileRaw));
      } else if (next === 5) {
        const raw = await osekkaiRequest('/freebusy');
        const window = normalizeFreeWindow(raw);
        setFreeWindow(window);
        addLog('合成Free Window', window?.durationMinutes ? `${window.durationMinutes / 60}時間の空き` : '空き時間を読み込みました。');
      } else if (next === 6) {
        const raw = await osekkaiRequest('/opportunities');
        const nextOpportunities = extractOpportunities(raw);
        setOpportunities(nextOpportunities);
        addLog('source snapshot', nextOpportunities.length ? `${nextOpportunities.length}件の根拠付き候補` : '有効な候補はありません。');
      } else if (next === 7) {
        const raw = await decide();
        const nextDecision = decisionFrom(raw);
        setDecision(nextDecision);
        const nextEpisodeId = episodeIdFrom(raw, nextDecision);
        setEpisodeId(nextEpisodeId ?? '');
        addLog(
          nextDecision?.shouldPush ? 'PUSH' : 'NO PUSH',
          nextDecision?.selectedOpportunity?.title ?? nextDecision?.reasonCodes.map(reasonLabel).join('・') ?? '判断を記録しました。',
          nextDecision?.shouldPush ? 'push' : 'no-push',
        );
      } else if (next === 8) {
        await sendFeedback('action', 'accepted');
        addLog('行動反応', '「行ってみる」を記録しました。', 'push');
      } else if (next === 9) {
        await sendFeedback('distance', 'just_right');
        addLog('距離評価', '「ちょうどいい」を記録しました。', 'push');
      } else if (next === 10) {
        await transition('attended');
        addLog('実参加（デモ）', '参加した時刻をEpisodeへ記録しました。');
      } else if (next === 11) {
        await transition('revisited');
        addLog('再訪（デモ）', '再び訪れた時刻をEpisodeへ記録しました。');
      } else if (next === 12) {
        await osekkaiRequest('/metrics');
        setMetricsReady(true);
        addLog('Impact更新', 'EpisodeからKPIを再計算しました。');
      }
      setCompleted(next);
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setRunning(false);
    }
  };

  const reactToProposal = async (response: 'accepted' | 'declined' | 'show_another' | 'pause_one_week') => {
    setReactionBusy(response);
    setError('');
    try {
      const raw = await sendFeedback('action', response);
      const labels = {
        accepted: '行ってみる',
        declined: '今日はやめる',
        show_another: '別のにして',
        pause_one_week: '今週は放っておいて',
      };
      addLog('提案への反応', `「${labels[response]}」を記録しました。`);
      if (response === 'accepted' && completed === 7) setCompleted(8);
      if (response === 'show_another') {
        const root = firstRecord(raw);
        const alternative = normalizeOpportunity(root.alternativeOpportunity)
          ?? extractOpportunities(raw)[0];
        if (alternative) {
          setOpportunities((current) => [alternative, ...current]);
        } else {
          addLog('別の候補', readString(root, 'message') ?? '別の確認済み候補はありません。');
        }
      }
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setReactionBusy('');
    }
  };

  const rateDistance = async (value: 'too_much' | 'just_right' | 'push_more') => {
    setReactionBusy(value);
    setError('');
    try {
      await sendFeedback('distance', value);
      const labels = { too_much: 'もう少し放っておいて', just_right: 'ちょうどいい', push_more: 'もう少し押して' };
      addLog('距離評価', `「${labels[value]}」を記録しました。`);
      if (value === 'just_right' && completed === 8) setCompleted(9);
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setReactionBusy('');
    }
  };

  const progress = Math.round((completed / steps.length) * 100);
  const activeOpportunity = decision?.selectedOpportunity ?? opportunities[0];
  const profileBand = batteryBand(profile?.socialBattery ?? null);
  const stepStatus = useMemo(() => `${completed} / ${steps.length} 完了`, [completed]);

  return (
    <>
      <PageIntro
        eyebrow="REPRODUCIBLE DEMO"
        title="12の場面で、距離感の学び方を見る"
        aside={<ModeBadge mode={mode} />}
      >
        <p>固定fixtureで何度でも同じ判断を再現します。外部サービスへは接続しません。</p>
      </PageIntro>

      <InlineNotice tone="warning" title="これは現在の開催情報ではありません">
        <p>
          Opportunityは公開データの過去スナップショット、Free Windowと移動時間は合成デモです。
          実際に出かける情報としては使わないでください。
        </p>
      </InlineNotice>

      <div className={styles.demoToolbar}>
        <div>
          <span>{stepStatus}</span>
          <div className={styles.progressTrack} role="progressbar" aria-label="デモの進捗" aria-valuenow={completed} aria-valuemin={0} aria-valuemax={12}>
            <span style={{ width: `${progress}%` }} />
          </div>
        </div>
        <button
          className={styles.dangerButton}
          type="button"
          onClick={() => setResetConfirmOpen((current) => !current)}
          disabled={resetting || running || initializing}
        >
          デモをリセット
        </button>
      </div>

      {resetConfirmOpen ? (
        <div className={styles.deleteConfirmation} role="group" aria-labelledby="demo-reset-title">
          <div>
            <strong id="demo-reset-title">この匿名セッションのデータを削除します</strong>
            <p>
              Profile、会話、判断、フィードバック、KPIと現在のデモ進捗を削除し、固定fixtureの初期状態へ戻します。
              この操作は元に戻せません。自動の初回準備では、この削除処理は行いません。
            </p>
          </div>
          <label className={styles.field}>
            <span>確認のため「リセット」と入力</span>
            <input
              value={resetConfirmText}
              onChange={(event) => setResetConfirmText(event.target.value)}
              autoComplete="off"
            />
          </label>
          <div className={styles.confirmActions}>
            <button
              className={styles.textButton}
              type="button"
              onClick={() => {
                setResetConfirmOpen(false);
                setResetConfirmText('');
              }}
            >
              やめる
            </button>
            <button
              className={styles.dangerButtonSolid}
              type="button"
              disabled={resetConfirmText !== 'リセット' || resetting}
              onClick={resetDemo}
            >
              {resetting ? 'リセット中…' : 'データを削除してリセット'}
            </button>
          </div>
        </div>
      ) : null}

      {initializing ? (
        <InlineNotice title="デモを準備しています">
          <p>初回だけ、既存データを削除せず、再現用の同意設定を安全に準備します。</p>
        </InlineNotice>
      ) : null}

      {error ? (
        <InlineNotice tone="error" title="この段階を完了できませんでした">
          <p>{error}</p>
          <p>
            {demoReady
              ? '状態は進めていません。同じボタンから再試行できます。'
              : '状態は進めていません。「デモをリセット」から安全に再準備できます。'}
          </p>
        </InlineNotice>
      ) : null}

      <div className={styles.demoLayout}>
        <section className={styles.stepperPanel} aria-labelledby="stepper-heading">
          <div className={styles.panelHeader}>
            <div>
              <p className={styles.eyebrow}>SCENARIO</p>
              <h2 id="stepper-heading">中心デモ</h2>
            </div>
            <span>{progress}%</span>
          </div>
          <ol className={styles.stepList}>
            {steps.map((step, index) => {
              const number = index + 1;
              const done = completed >= number;
              const current = completed + 1 === number;
              return (
                <li key={step.title} className={done ? styles.stepDone : current ? styles.stepCurrent : styles.stepPending}>
                  <div className={styles.stepRail}>
                    <span aria-hidden="true">{done ? '✓' : number}</span>
                  </div>
                  <div className={styles.stepBody}>
                    <div>
                      <strong>{step.title}</strong>
                      <p>{step.detail}</p>
                    </div>
                    {current ? (
                      <button className={styles.stepButton} type="button" onClick={runCurrentStep} disabled={running || initializing || !demoReady}>
                        {initializing ? '準備中…' : running ? '実行中…' : step.action}
                      </button>
                    ) : done ? <span className={styles.doneLabel}>完了</span> : null}
                  </div>
                </li>
              );
            })}
          </ol>
          {completed === 12 && metricsReady ? (
            <div className={styles.demoComplete}>
              <span aria-hidden="true">✓</span>
              <div>
                <strong>12段階のデモが完了しました</strong>
                <p>最後に、判断理由とKPIがどう更新されたか確認しましょう。</p>
                <Link className={styles.primaryButton} href="/osekkai/impact">Impactを見る</Link>
              </div>
            </div>
          ) : null}
        </section>

        <aside className={styles.demoEvidence} aria-label="デモで使われた情報と判断">
          <section className={styles.evidenceCard}>
            <div className={styles.evidenceHeader}>
              <span className={styles.evidenceIcon} aria-hidden="true">◔</span>
              <div><small>PROFILE</small><h2>いまの距離感</h2></div>
              <ClassificationBadge classification="demo" />
            </div>
            {profile ? (
              <div className={styles.profileSnapshot}>
                <div>
                  <span>Social Battery</span>
                  <strong>{profile.socialBattery ?? '—'}<small>/100</small></strong>
                </div>
                <p>{profileBand.label}</p>
                <dl>
                  <div><dt>会話の強さ上限</dt><dd>{profile.maxSocialIntensity} / 5</dd></div>
                  <div><dt>口調</dt><dd>{profile.preferredTone}</dd></div>
                  <div><dt>PUSH同意</dt><dd>{profile.pushConsent ? 'あり' : 'なし'}</dd></div>
                </dl>
              </div>
            ) : <p className={styles.mutedPlaceholder}>ステップ2でProfileが表示されます。</p>}
          </section>

          <section className={styles.evidenceCard}>
            <div className={styles.evidenceHeader}>
              <span className={styles.evidenceIcon} aria-hidden="true">◷</span>
              <div><small>FREE WINDOW</small><h2>空いている時間</h2></div>
              <span className={styles.syntheticBadge}>合成デモ</span>
            </div>
            {freeWindow ? (
              <div className={styles.freeWindowCard}>
                <strong>{freeWindow.durationMinutes ? `${freeWindow.durationMinutes / 60}時間` : '空きあり'}</strong>
                <span>{formatDateTime(freeWindow.start)} 〜 {formatDateTime(freeWindow.end)}</span>
                <small>予定のタイトル・説明・場所・参加者は含みません。</small>
              </div>
            ) : <p className={styles.mutedPlaceholder}>ステップ5で合成Free Windowが表示されます。</p>}
          </section>

          <section className={styles.evidenceCard}>
            <div className={styles.evidenceHeader}>
              <span className={styles.evidenceIcon} aria-hidden="true">◇</span>
              <div><small>OPPORTUNITY</small><h2>根拠のある候補</h2></div>
              <span className={styles.snapshotBadge}>過去snapshot</span>
            </div>
            {activeOpportunity ? (
              <article className={styles.opportunityCard}>
                <p className={styles.opportunityProvider}>{activeOpportunity.provider ?? '公開データ提供者'}</p>
                <h3>{activeOpportunity.title}</h3>
                <dl>
                  <div><dt>時間</dt><dd>{formatDateTime(activeOpportunity.startsAt)}</dd></div>
                  <div><dt>費用</dt><dd>{activeOpportunity.priceYen === 0 ? '無料' : activeOpportunity.priceYen ? `¥${activeOpportunity.priceYen.toLocaleString('ja-JP')}` : '記載なし'}</dd></div>
                  <div><dt>移動</dt><dd>{activeOpportunity.travelMinutes ? `合成 ${activeOpportunity.travelMinutes}分` : '合成見積り'}</dd></div>
                  <div><dt>関わり</dt><dd>強さ {activeOpportunity.socialIntensity ?? '—'} / 5</dd></div>
                </dl>
                {activeOpportunity.dataset ? <small>データセット: {activeOpportunity.dataset}</small> : null}
                {activeOpportunity.sourceUrl ? (
                  <a href={activeOpportunity.sourceUrl} target="_blank" rel="noreferrer">出典を開く（現在情報ではありません）</a>
                ) : null}
              </article>
            ) : completed >= 6 ? (
              <div className={styles.noCandidateState}>
                <strong>有効な候補はありません</strong>
                <p>候補を創作せず、NO_VERIFIED_OPPORTUNITYとしてPUSHしません。</p>
              </div>
            ) : <p className={styles.mutedPlaceholder}>ステップ6でsource snapshot候補を表示します。</p>}
          </section>

          <section className={styles.evidenceCard}>
            <div className={styles.evidenceHeader}>
              <span className={styles.evidenceIcon} aria-hidden="true">◎</span>
              <div><small>POLICY</small><h2>判断と、その理由</h2></div>
              <span className={styles.ruleBadge}>判断ルール</span>
            </div>
            {firstDecision ? (
              <div className={styles.decisionBlock}>
                <span className={styles.noPushBadge}>NO PUSH</span>
                <strong>最初は、声をかけない。</strong>
                <ul>{firstDecision.reasonCodes.map((code) => <li key={code}><span>{code}</span>{reasonLabel(code)}</li>)}</ul>
              </div>
            ) : <p className={styles.mutedPlaceholder}>ステップ3で最初のno-PUSH理由を表示します。</p>}
            {decision ? (
              <div className={styles.decisionBlock}>
                <span className={decision.shouldPush ? styles.pushBadge : styles.noPushBadge}>
                  {decision.shouldPush ? 'PUSH 1件' : 'NO PUSH'}
                </span>
                <strong>{decision.message ?? (decision.shouldPush ? '条件に合う候補を1件だけ選びました。' : '今回は提案しません。')}</strong>
                <ul>{decision.reasonCodes.map((code) => <li key={code}><span>{code}</span>{reasonLabel(code)}</li>)}</ul>
              </div>
            ) : null}
            <p className={styles.policyDisclaimer}>このスコアは設定可能なMVP判断ルールで、医学的・科学的に確立した式ではありません。</p>
          </section>

          {decision?.shouldPush && completed >= 7 ? (
            <section className={styles.feedbackCard}>
              <div>
                <p className={styles.eyebrow}>YOUR SAY</p>
                <h2>この提案、どうする？</h2>
              </div>
              <div className={styles.responseGrid}>
                <button type="button" onClick={() => reactToProposal('accepted')} disabled={Boolean(reactionBusy)}>
                  {reactionBusy === 'accepted' ? '記録中…' : '行ってみる'}
                </button>
                <button type="button" onClick={() => reactToProposal('declined')} disabled={Boolean(reactionBusy)}>今日はやめる</button>
                <button type="button" onClick={() => reactToProposal('show_another')} disabled={Boolean(reactionBusy)}>別のにして</button>
                <button type="button" onClick={() => reactToProposal('pause_one_week')} disabled={Boolean(reactionBusy)}>今週は放っておいて</button>
              </div>
              {completed >= 8 ? (
                <div className={styles.distanceFeedback}>
                  <strong>声のかけ方は、どうだった？</strong>
                  <div>
                    <button type="button" onClick={() => rateDistance('too_much')} disabled={Boolean(reactionBusy)}>もう少し放っておいて</button>
                    <button type="button" onClick={() => rateDistance('just_right')} disabled={Boolean(reactionBusy)}>ちょうどいい</button>
                    <button type="button" onClick={() => rateDistance('push_more')} disabled={Boolean(reactionBusy)}>もう少し押して</button>
                  </div>
                </div>
              ) : null}
            </section>
          ) : null}

          <section className={styles.logCard}>
            <div className={styles.panelHeaderCompact}>
              <h2>このセッションの記録</h2>
              <span>{logs.length}件</span>
            </div>
            {logs.length ? (
              <ol className={styles.demoLog}>
                {logs.map((log) => (
                  <li key={log.id}>
                    <span className={log.tone === 'push' ? styles.logPush : log.tone === 'no-push' ? styles.logNoPush : styles.logPlain} />
                    <div><strong>{log.title}</strong><p>{log.detail}</p></div>
                  </li>
                ))}
              </ol>
            ) : <p className={styles.mutedPlaceholder}>実行した段階がここに残ります。</p>}
          </section>
        </aside>
      </div>
    </>
  );
}
