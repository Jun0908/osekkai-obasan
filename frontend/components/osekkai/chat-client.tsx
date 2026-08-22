'use client';

import Link from 'next/link';
import { type FormEvent, useEffect, useRef, useState } from 'react';

import styles from '@/app/osekkai/osekkai.module.css';
import {
  friendlyApiError,
  newIdempotencyKey,
  osekkaiRequest,
  type JsonObject,
} from './api-client';
import {
  batteryBand,
  firstRecord,
  formatDateTime,
  isRecord,
  normalizeProfile,
  readBoolean,
  readNumber,
  readString,
  type PreferenceMemory,
  type ProfileView,
} from './models';
import { InlineNotice, LoadingBlock, PageIntro } from './ui';

type ChatTurn = {
  id: string;
  speaker: 'you' | 'osekkai';
  text: string;
  remembered?: boolean;
  hint?: string;
  confidence?: number;
  learned?: string[];
};

const initialTurn: ChatTurn = {
  id: 'welcome',
  speaker: 'osekkai',
  text: '今日は、どんな一日だった？ 何かを決めなくていいから、ひとことだけでも聞かせて。',
};

const starters = [
  '今週疲れた。何もしたくない',
  '少し外に出たいが、話したくない',
  '今日はそっとしておいて',
];

async function fetchProfileView(): Promise<ProfileView> {
  return normalizeProfile(await osekkaiRequest('/profile'));
}

function summarizeDelta(raw: unknown) {
  if (!isRecord(raw)) return [];
  const labels: Record<string, string> = {
    socialBattery: 'Social Battery',
    maxSocialIntensity: '人との関わりの強さ',
    preferredTone: '話し方',
    pauseUntil: 'お休み期間',
    preferredCategories: '好きかもしれないこと',
    avoidedCategories: '避けたいこと',
  };
  return Object.entries(raw).map(([key, value]) => {
    const detail = isRecord(value) && 'value' in value ? value.value : value;
    const printable = Array.isArray(detail) ? detail.join('、') : String(detail ?? '更新');
    return `${labels[key] ?? key}: ${printable}`;
  });
}

function MemoryItem({ item, onDeleteEvidence, onDeletePreference, deletingKey }: {
  item: PreferenceMemory;
  onDeleteEvidence: (id: string) => void;
  onDeletePreference: (key: string) => void;
  deletingKey: string;
}) {
  return (
    <li className={styles.memoryItem}>
      <div>
        <div className={styles.memoryTitleRow}>
          <strong>{item.label}</strong>
          {typeof item.confidence === 'number' ? (
            <span>確からしさ {Math.round(item.confidence * 100)}%</span>
          ) : null}
        </div>
        <p>{item.value}</p>
        {item.evidence.length ? (
          <ul className={styles.memoryEvidenceList} aria-label={`${item.label}の保存根拠`}>
            {item.evidence.map((evidence) => (
              <li key={evidence.id}>
                <small>
                  きっかけ: 「{evidence.text}」
                  {evidence.createdAt ? (
                    <>・<time dateTime={evidence.createdAt}>{formatDateTime(evidence.createdAt)}</time></>
                  ) : null}
                </small>
                <button
                  className={styles.ghostDangerButton}
                  type="button"
                  onClick={() => onDeleteEvidence(evidence.id)}
                  disabled={Boolean(deletingKey)}
                  aria-label={`${item.label}の根拠「${evidence.text}」を削除`}
                >
                  {deletingKey === `evidence:${evidence.id}` ? '削除中…' : 'この根拠を削除'}
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <button
        className={styles.ghostDangerButton}
        type="button"
        onClick={() => onDeletePreference(item.key)}
        disabled={Boolean(deletingKey)}
        aria-label={`${item.label}の推定項目をすべて削除`}
      >
        {deletingKey === `preference:${item.key}` ? '削除中…' : '項目を削除'}
      </button>
    </li>
  );
}

export default function ChatClient() {
  const [profile, setProfile] = useState<ProfileView>();
  const [turns, setTurns] = useState<ChatTurn[]>([initialTurn]);
  const [message, setMessage] = useState('');
  const [remember, setRemember] = useState(false);
  const [loadingProfile, setLoadingProfile] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [deletingKey, setDeletingKey] = useState('');
  const [error, setError] = useState('');
  const [safetySupport, setSafetySupport] = useState(false);
  const statusRef = useRef<HTMLDivElement>(null);

  const loadProfile = async () => {
    setLoadingProfile(true);
    try {
      const next = await fetchProfileView();
      setProfile(next);
      setRemember(next.memoryConsent);
      setError('');
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setLoadingProfile(false);
    }
  };

  useEffect(() => {
    let active = true;
    void fetchProfileView()
      .then((next) => {
        if (!active) return;
        setProfile(next);
        setRemember(next.memoryConsent);
        setError('');
      })
      .catch((reason: unknown) => {
        if (active) setError(friendlyApiError(reason));
      })
      .finally(() => {
        if (active) setLoadingProfile(false);
      });

    return () => {
      active = false;
    };
  }, []);

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault();
    const text = message.trim();
    if (!text || submitting) return;

    const userTurn: ChatTurn = {
      id: newIdempotencyKey('turn-user'),
      speaker: 'you',
      text,
      remembered: remember,
    };
    setTurns((current) => [...current, userTurn]);
    setMessage('');
    setSubmitting(true);
    setError('');

    try {
      const raw = await osekkaiRequest<JsonObject>('/chat', {
        method: 'POST',
        mutation: true,
        body: {
          message: text,
          remember,
          idempotencyKey: newIdempotencyKey('chat'),
        },
      });
      const result = firstRecord(raw.chatResult, raw.result, raw);
      const safety = firstRecord(result.safety);
      const reply = readString(result, 'reply', 'replyText', 'message')
        ?? 'うまく言葉にできなかったみたい。もう一度、短く聞かせてもらえる？';
      const learned = remember ? summarizeDelta(result.profileDelta) : [];
      setSafetySupport(readBoolean(safety, false, 'requiresHumanSupport'));
      setTurns((current) => [
        ...current,
        {
          id: newIdempotencyKey('turn-osekkai'),
          speaker: 'osekkai',
          text: reply,
          hint: readString(result, 'interventionHint'),
          confidence: readNumber(result, 'confidence'),
          learned,
        },
      ]);
      if (remember) {
        await loadProfile();
      }
      window.requestAnimationFrame(() => statusRef.current?.focus());
    } catch (reason) {
      setError(friendlyApiError(reason));
      setTurns((current) => current.filter((turn) => turn.id !== userTurn.id));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  };

  const deletePreference = async (key: string) => {
    setDeletingKey(`preference:${key}`);
    setError('');
    try {
      const raw = await osekkaiRequest('/profile', {
        method: 'PATCH',
        mutation: true,
        body: {
          operation: 'remove_inferred_preference',
          inferredPreferenceKey: key,
          idempotencyKey: newIdempotencyKey('memory-delete'),
        },
      });
      setProfile(normalizeProfile(raw));
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setDeletingKey('');
    }
  };

  const deleteEvidence = async (evidenceId: string) => {
    setDeletingKey(`evidence:${evidenceId}`);
    setError('');
    try {
      const raw = await osekkaiRequest('/profile', {
        method: 'PATCH',
        mutation: true,
        body: {
          removeEvidenceId: evidenceId,
          idempotencyKey: newIdempotencyKey('evidence-delete'),
        },
      });
      setProfile(normalizeProfile(raw));
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setDeletingKey('');
    }
  };

  const battery = batteryBand(profile?.socialBattery ?? null);
  const latestAgentTurn = [...turns].reverse().find((turn) => turn.speaker === 'osekkai' && turn.hint);

  return (
    <>
      <PageIntro
        eyebrow="CONVERSATION"
        title="今日は、どのくらいの距離がいい？"
        aside={
          <Link className={styles.smallTextLink} href="/osekkai/settings">
            記憶と通知を設定
          </Link>
        }
      >
        <p>答えたくないことは、答えなくて大丈夫。提案を受けるための面談ではありません。</p>
      </PageIntro>

      {safetySupport ? (
        <InlineNotice tone="warning" title="いまは人の支えを優先しましょう">
          <p>
            このAIだけで抱えず、信頼できる人や地域の相談窓口につながってください。
            今すぐ身の危険がある場合は119または110へ連絡してください。
          </p>
        </InlineNotice>
      ) : null}

      <div className={styles.chatLayout}>
        <section className={styles.chatPanel} aria-labelledby="chat-heading">
          <div className={styles.panelHeader}>
            <div>
              <p className={styles.eyebrow}>TALK, DON&apos;T PERFORM</p>
              <h2 id="chat-heading">話すだけの場所</h2>
            </div>
            <span className={styles.privatePill}>匿名セッション</span>
          </div>

          <div className={styles.chatLog} aria-live="polite" aria-relevant="additions">
            {turns.map((turn) => (
              <article
                key={turn.id}
                className={turn.speaker === 'you' ? styles.userMessage : styles.agentMessage}
              >
                <p className={styles.messageSpeaker}>{turn.speaker === 'you' ? 'あなた' : 'おっせかいおばさん'}</p>
                <p>{turn.text}</p>
                {turn.speaker === 'you' ? (
                  <small>{turn.remembered ? 'この会話から学習します' : 'この会話は記憶しません'}</small>
                ) : null}
                {turn.learned?.length ? (
                  <div className={styles.learnedDelta}>
                    <strong>今回わかったかもしれないこと</strong>
                    <ul>{turn.learned.map((item) => <li key={item}>{item}</li>)}</ul>
                    <span>設定画面や右の記憶から、いつでも消せます。</span>
                  </div>
                ) : null}
                {turn.hint === 'do_not_push' ? (
                  <div className={styles.noProposal}>
                    <span aria-hidden="true">—</span>
                    <p><strong>今回は提案しません。</strong>あなたの「今は動かない」を優先しました。</p>
                  </div>
                ) : null}
              </article>
            ))}
            {submitting ? (
              <div className={styles.typingIndicator} role="status">
                <span /><span /><span />
                <span className={styles.srOnly}>返事を考えています</span>
              </div>
            ) : null}
            <div ref={statusRef} tabIndex={-1} className={styles.srOnly}>
              {latestAgentTurn ? '返事が届きました' : ''}
            </div>
          </div>

          <form className={styles.chatComposer} onSubmit={sendMessage}>
            <label className={styles.composerLabel} htmlFor="osekkai-message">
              いまの気持ちをひとこと
            </label>
            <textarea
              id="osekkai-message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="例：今日は静かに過ごしたい"
              rows={3}
              maxLength={1000}
              disabled={submitting}
            />
            <div className={styles.composerFooter}>
              <label className={styles.rememberControl}>
                <input
                  type="checkbox"
                  checked={!remember}
                  onChange={(event) => setRemember(!event.target.checked)}
                  disabled={submitting || !profile?.memoryConsent}
                />
                <span>{profile?.memoryConsent ? 'これは覚えないで' : '記憶への同意がオフ'}</span>
              </label>
              <span className={styles.characterCount}>{message.length} / 1000</span>
              <button className={styles.primaryButton} type="submit" disabled={submitting || !message.trim()}>
                {submitting ? '聞いています…' : '送る'}
              </button>
            </div>
          </form>
          <div className={styles.starterRow} aria-label="入力例">
            {starters.map((starter) => (
              <button key={starter} type="button" onClick={() => setMessage(starter)} disabled={submitting}>
                {starter}
              </button>
            ))}
          </div>
          {error ? <InlineNotice tone="error"><p>{error}</p></InlineNotice> : null}
        </section>

        <aside className={styles.chatSidebar} aria-label="現在の距離感プロフィール">
          {loadingProfile ? <LoadingBlock label="距離感を確認しています" /> : (
            <>
              <section className={styles.batteryCard}>
                <div className={styles.panelHeaderCompact}>
                  <div>
                    <p className={styles.eyebrow}>TODAY</p>
                    <h2>Social Battery</h2>
                  </div>
                  <strong className={styles.batteryValue}>
                    {profile?.socialBattery === null || profile?.socialBattery === undefined
                      ? '—'
                      : profile.socialBattery}
                  </strong>
                </div>
                <div
                  className={styles.batteryTrack}
                  role="meter"
                  aria-label="Social Battery"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={profile?.socialBattery ?? undefined}
                  aria-valuetext={battery.label}
                >
                  <span style={{ width: `${profile?.socialBattery ?? 0}%` }} />
                </div>
                <p>{battery.label}</p>
                <small>空き時間だけからは推定しません。</small>
              </section>

              <section className={styles.memoryCard}>
                <div className={styles.panelHeaderCompact}>
                  <div>
                    <p className={styles.eyebrow}>MEMORY</p>
                    <h2>覚えていること</h2>
                  </div>
                  <span>{profile?.inferred.length ?? 0}件</span>
                </div>
                {!profile?.memoryConsent ? (
                  <InlineNotice tone="info">
                    <p>記憶への同意はオフです。設定でオンにするまで、会話と推定は保存しません。</p>
                  </InlineNotice>
                ) : null}
                {profile?.inferred.length ? (
                  <ul className={styles.memoryList}>
                    {profile.inferred.map((item) => (
                      <MemoryItem
                        key={item.key}
                        item={item}
                        deletingKey={deletingKey}
                        onDeleteEvidence={deleteEvidence}
                        onDeletePreference={deletePreference}
                      />
                    ))}
                  </ul>
                ) : (
                  <div className={styles.compactEmpty}>
                    <p>まだ覚えていることはありません。</p>
                    <span>会話からの推定は、確からしさと根拠を付けて表示します。</span>
                  </div>
                )}
              </section>

              <section className={styles.whyCard}>
                <p className={styles.eyebrow}>WHY</p>
                <h2>なぜ提案した／しなかった？</h2>
                <p>判断の理由コードと、使った情報をあとから確認できます。</p>
                <Link href="/osekkai/impact">判断の履歴を見る <span aria-hidden="true">→</span></Link>
              </section>
            </>
          )}
        </aside>
      </div>
    </>
  );
}
