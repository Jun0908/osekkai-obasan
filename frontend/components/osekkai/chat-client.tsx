'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { type FormEvent, useEffect, useRef, useState } from 'react';

import styles from '@/app/osekkai/osekkai.module.css';
import {
  friendlyApiError,
  newIdempotencyKey,
  osekkaiRequest,
  type JsonObject,
} from './api-client';
import {
  firstRecord,
  normalizeProfile,
  readBoolean,
  readString,
  type ProfileView,
} from './models';
import { InlineNotice, PageIntro } from './ui';

type ChatTurn = {
  id: string;
  speaker: 'you' | 'osekkai';
  text: string;
};

const initialTurn: ChatTurn = {
  id: 'welcome',
  speaker: 'osekkai',
  text: 'あんた、何が好きなのよ。最近やってみたいこと、ひとつ教えて。',
};

const starters = [
  'ヨガをやってみたい',
  'ボルダリングが好き',
  '料理しながら人と話したい',
  '音楽好きと知り合いたい',
];

async function fetchProfileView(): Promise<ProfileView> {
  return normalizeProfile(await osekkaiRequest('/profile'));
}

export default function ChatClient() {
  const router = useRouter();
  const [profile, setProfile] = useState<ProfileView>();
  const [turns, setTurns] = useState<ChatTurn[]>([initialTurn]);
  const [message, setMessage] = useState('');
  const [remember, setRemember] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [consenting, setConsenting] = useState(false);
  const [enablingRecommendations, setEnablingRecommendations] = useState(false);
  const [error, setError] = useState('');
  const [safetySupport, setSafetySupport] = useState(false);
  const statusRef = useRef<HTMLDivElement>(null);

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
      });

    return () => {
      active = false;
    };
  }, []);

  const updateRemember = async (checked: boolean) => {
    if (!checked || profile?.memoryConsent) {
      setRemember(checked);
      return;
    }
    setConsenting(true);
    setError('');
    try {
      const raw = await osekkaiRequest('/profile', {
        method: 'PATCH',
        mutation: true,
        body: {
          operation: 'update_settings',
          updates: { memoryConsent: true },
          idempotencyKey: newIdempotencyKey('memory-consent'),
        },
      });
      const next = normalizeProfile(raw);
      setProfile(next);
      setRemember(true);
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setConsenting(false);
    }
  };

  const sendMessage = async (event: FormEvent) => {
    event.preventDefault();
    const text = message.trim();
    if (!text || submitting) return;

    const userTurn: ChatTurn = {
      id: newIdempotencyKey('turn-user'),
      speaker: 'you',
      text,
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
      setSafetySupport(readBoolean(safety, false, 'requiresHumanSupport'));
      setTurns((current) => [
        ...current,
        {
          id: newIdempotencyKey('turn-osekkai'),
          speaker: 'osekkai',
          text: reply,
        },
      ]);
      window.requestAnimationFrame(() => statusRef.current?.focus());
    } catch (reason) {
      setError(friendlyApiError(reason));
      setTurns((current) => current.filter((turn) => turn.id !== userTurn.id));
      setMessage(text);
    } finally {
      setSubmitting(false);
    }
  };

  const receiveRecommendations = async () => {
    setEnablingRecommendations(true);
    setError('');
    try {
      const updates: Record<string, boolean> = {};
      if (!profile?.pushConsent) updates.pushConsent = true;
      if (!profile?.memoryConsent) updates.memoryConsent = true;
      if (Object.keys(updates).length) {
        const raw = await osekkaiRequest('/profile', {
          method: 'PATCH',
          mutation: true,
          body: {
            operation: 'update_settings',
            updates,
            idempotencyKey: newIdempotencyKey('push-consent'),
          },
        });
        setProfile(normalizeProfile(raw));
      }
      const latestUserText = [...turns].reverse().find((turn) => turn.speaker === 'you')?.text;
      if (!remember && latestUserText) {
        await osekkaiRequest('/chat', {
          method: 'POST',
          mutation: true,
          body: {
            message: latestUserText,
            remember: true,
            idempotencyKey: newIdempotencyKey('recommendation-preference'),
          },
        });
        setRemember(true);
      }
      router.push('/osekkai/demo');
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setEnablingRecommendations(false);
    }
  };

  const hasAnswered = turns.some((turn) => turn.speaker === 'you');

  return (
    <>
      <PageIntro
        eyebrow="CONVERSATION"
        title="あんた、何が好きなのよ。"
        aside={
          <Link className={styles.smallTextLink} href="/osekkai/settings">
            設定
          </Link>
        }
      >
        <p>検索条件を並べなくて大丈夫。好きなことか、次にやってみたいことを、ひとつだけ。</p>
      </PageIntro>

      {safetySupport ? (
        <InlineNotice tone="warning" title="いまは人の支えを優先しましょう">
          <p>
            このAIだけで抱えず、信頼できる人や地域の相談窓口につながってください。
            今すぐ身の危険がある場合は119または110へ連絡してください。
          </p>
        </InlineNotice>
      ) : null}

      <div className={styles.focusedChatLayout}>
        <section className={styles.chatPanel} aria-labelledby="chat-heading">
          <div className={styles.panelHeader}>
            <div>
              <p className={styles.eyebrow}>ONE QUESTION AT A TIME</p>
              <h2 id="chat-heading">好みをひとつ教えて</h2>
            </div>
            <span className={styles.privatePill}>一問ずつ</span>
          </div>

          <div className={styles.chatLog} aria-live="polite" aria-relevant="additions">
            {turns.map((turn) => (
              <article
                key={turn.id}
                className={turn.speaker === 'you' ? styles.userMessage : styles.agentMessage}
              >
                <p className={styles.messageSpeaker}>{turn.speaker === 'you' ? 'あなた' : 'おっせかいおばさん'}</p>
                <p>{turn.text}</p>
              </article>
            ))}
            {submitting ? (
              <div className={styles.typingIndicator} role="status">
                <span /><span /><span />
                <span className={styles.srOnly}>返事を考えています</span>
              </div>
            ) : null}
            <div ref={statusRef} tabIndex={-1} className={styles.srOnly}>
              {hasAnswered ? '返事が届きました' : ''}
            </div>
          </div>

          <form className={styles.chatComposer} onSubmit={sendMessage}>
            <label className={styles.composerLabel} htmlFor="osekkai-message">
              好きなこと・やってみたいこと
            </label>
            <textarea
              id="osekkai-message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="例：ボルダリングをやってみたい"
              rows={3}
              maxLength={1000}
              disabled={submitting}
            />
            <div className={styles.composerFooter}>
              <label className={styles.rememberControl}>
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => void updateRemember(event.target.checked)}
                  disabled={submitting || consenting || !profile}
                />
                <span>{consenting ? '設定中…' : 'この好みを次の提案に使う'}</span>
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
          {hasAnswered && !submitting ? (
            <div className={styles.chatNextAction}>
              <p>この好みを次の提案に使い、条件が合う時のおっせかいをオンにします。設定でいつでも戻せます。</p>
              <button
                className={styles.primaryButton}
                type="button"
                disabled={enablingRecommendations || !profile}
                onClick={() => void receiveRecommendations()}
              >
                {enablingRecommendations ? '設定中…' : 'この好みで提案を受け取る'} <span aria-hidden="true">→</span>
              </button>
            </div>
          ) : null}
          {error ? <InlineNotice tone="error"><p>{error}</p></InlineNotice> : null}
        </section>
      </div>
    </>
  );
}
