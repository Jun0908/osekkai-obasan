'use client';

import Link from 'next/link';
import { type FormEvent, useEffect, useRef, useState } from 'react';

import RecommendationShortlist from '@/app/osekkai/_components/recommendation-shortlist';
import styles from '@/app/osekkai/osekkai.module.css';
import type {
  ChatResult,
  ConversationContext,
  Opportunity,
  RankedOpportunity,
} from '@/lib/osekkai/types.generated';
import {
  friendlyApiError,
  newIdempotencyKey,
  osekkaiRequest,
} from './api-client';
import { normalizeProfile, type ProfileView } from './models';
import { InlineNotice, PageIntro } from './ui';

type ChatTurn = {
  id: string;
  speaker: 'you' | 'osekkai';
  text: string;
};

type RecommendationAction = 'accepted' | 'declined' | 'pause_one_week' | 'revisit';

const starters = [
  'ヨガをやってみたい',
  'ボルダリングが好き',
  '料理しながら人と話したい',
  '音楽好きと知り合いたい',
];

function recommendationProps(context?: ConversationContext): {
  opportunities: Opportunity[];
  ranking: RankedOpportunity[];
} {
  if (!context) return { opportunities: [], ranking: [] };
  return {
    opportunities: context.recommendations.map((item) => item.opportunity),
    ranking: context.recommendations.map((item) => ({
      rank: item.rank,
      score: 0,
      opportunityId: item.opportunity.id,
      recommendationReasons: item.recommendationReasons,
      exclusionReasons: [],
    })),
  };
}

export default function ChatClient() {
  const startKeyRef = useRef(newIdempotencyKey('chat-start'));
  const chatLogRef = useRef<HTMLDivElement>(null);
  const [profile, setProfile] = useState<ProfileView>();
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [context, setContext] = useState<ConversationContext>();
  const [message, setMessage] = useState('');
  const [remember, setRemember] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [consenting, setConsenting] = useState(false);
  const [error, setError] = useState('');
  const [safetySupport, setSafetySupport] = useState(false);

  useEffect(() => {
    let active = true;
    const initialize = async () => {
      try {
        const [profileRaw, started] = await Promise.all([
          osekkaiRequest('/profile'),
          osekkaiRequest<ChatResult>('/chat', {
            method: 'POST',
            mutation: true,
            body: {
              action: 'start',
              remember: false,
              idempotencyKey: startKeyRef.current,
            },
          }),
        ]);
        if (!active) return;
        const nextProfile = normalizeProfile(profileRaw);
        setProfile(nextProfile);
        setRemember(nextProfile.memoryConsent);
        setContext(started.context);
        setSafetySupport(started.safety.requiresHumanSupport);
        setTurns([{ id: 'episode-start', speaker: 'osekkai', text: started.reply }]);
        setError('');
      } catch (reason) {
        if (active) setError(friendlyApiError(reason));
      }
    };
    void initialize();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const chatLog = chatLogRef.current;
    if (!chatLog) return;
    chatLog.scrollTop = chatLog.scrollHeight;
  }, [turns, submitting]);

  const applyChatResult = (result: ChatResult) => {
    setContext(result.context);
    setSafetySupport(result.safety.requiresHumanSupport);
    setTurns((current) => [
      ...current,
      {
        id: newIdempotencyKey('turn-osekkai'),
        speaker: 'osekkai',
        text: result.reply,
      },
    ]);
  };

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

  const submitText = async (text: string) => {
    const clean = text.trim();
    if (!clean || submitting || context?.canSendMessage === false) return;
    const userTurn: ChatTurn = {
      id: newIdempotencyKey('turn-user'),
      speaker: 'you',
      text: clean,
    };
    setTurns((current) => [...current, userTurn]);
    setMessage('');
    setSubmitting(true);
    setError('');
    try {
      const action = context?.state === 'check_in_due' ? 'check_in' : 'message';
      const result = await osekkaiRequest<ChatResult>('/chat', {
        method: 'POST',
        mutation: true,
        body: {
          action,
          message: clean,
          remember,
          idempotencyKey: newIdempotencyKey(`chat-${action}`),
        },
      });
      applyChatResult(result);
    } catch (reason) {
      setError(friendlyApiError(reason));
      setTurns((current) => current.filter((turn) => turn.id !== userTurn.id));
      setMessage(clean);
    } finally {
      setSubmitting(false);
    }
  };

  const sendMessage = (event: FormEvent) => {
    event.preventDefault();
    void submitText(message);
  };

  const handleRecommendation = async (
    action: RecommendationAction,
    opportunity: Opportunity,
  ) => {
    if (submitting || action === 'revisit') return;
    if (action === 'declined') {
      await submitText('これは違う');
      return;
    }
    if (action === 'pause_one_week') {
      await submitText('今回は無理');
      return;
    }
    setTurns((current) => [
      ...current,
      {
        id: newIdempotencyKey('turn-user'),
        speaker: 'you',
        text: `「${opportunity.title}」に行ってみる`,
      },
    ]);
    setSubmitting(true);
    setError('');
    try {
      const result = await osekkaiRequest<ChatResult>('/chat', {
        method: 'POST',
        mutation: true,
        body: {
          action: 'select',
          opportunityId: opportunity.id,
          remember,
          idempotencyKey: newIdempotencyKey('chat-select'),
        },
      });
      applyChatResult(result);
    } catch (reason) {
      setError(friendlyApiError(reason));
    } finally {
      setSubmitting(false);
    }
  };

  const recommendations = recommendationProps(context);
  const showStarters = context?.state === 'getting_to_know';

  return (
    <>
      <PageIntro
        eyebrow="CONVERSATION"
        title="おばさんに話す"
        aside={
          <Link className={styles.smallTextLink} href="/osekkai/settings">
            設定
          </Link>
        }
      >
        <p>好みも、行きたくても動けない理由も、一度に一つだけ。話した分だけ誘い方が合ってきます。</p>
      </PageIntro>

      {safetySupport ? (
        <InlineNotice tone="warning" title="いまは人の支えを優先します">
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
              <h2 id="chat-heading">会話の続き</h2>
            </div>
            <span className={styles.privatePill}>一問ずつ</span>
          </div>

          <div
            ref={chatLogRef}
            className={styles.chatLog}
            aria-live="polite"
            aria-relevant="additions"
          >
            {turns.map((turn) => (
              <article
                key={turn.id}
                className={turn.speaker === 'you' ? styles.userMessage : styles.agentMessage}
              >
                <p className={styles.messageSpeaker}>
                  {turn.speaker === 'you' ? 'あなた' : 'おっせかいおばさん'}
                </p>
                <p>{turn.text}</p>
              </article>
            ))}
            {submitting || !context ? (
              <div className={styles.typingIndicator} role="status">
                <span /><span /><span />
                <span className={styles.srOnly}>返事を考えています</span>
              </div>
            ) : null}
          </div>

          {context?.notice ? (
            <div className={styles.chatContextNotice} role="note">{context.notice}</div>
          ) : null}

          {recommendations.opportunities.length > 0 ? (
            <div className={styles.chatRecommendations} aria-label="会話から選んだイベント候補">
              <RecommendationShortlist
                opportunities={recommendations.opportunities}
                ranking={recommendations.ranking}
                onAction={(action, opportunity) => void handleRecommendation(action, opportunity)}
                busy={submitting ? '会話を更新中' : undefined}
                hideRevisit
              />
            </div>
          ) : null}

          {context?.quickReplies.length ? (
            <div className={styles.starterRow} aria-label="返事の候補">
              {context.quickReplies.map((reply) => (
                <button
                  key={reply.id}
                  type="button"
                  onClick={() => void submitText(reply.message)}
                  disabled={submitting}
                >
                  {reply.label}
                </button>
              ))}
            </div>
          ) : null}

          <form className={styles.chatComposer} onSubmit={sendMessage}>
            <label className={styles.composerLabel} htmlFor="osekkai-message">
              好きなこと、ひっかかること、行ったあとの感想
            </label>
            <textarea
              id="osekkai-message"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="例：ボルダリングが好き／初参加がちょっと不安"
              rows={3}
              maxLength={1000}
              disabled={submitting || context?.canSendMessage === false}
            />
            <div className={styles.composerFooter}>
              <label className={styles.rememberControl}>
                <input
                  type="checkbox"
                  checked={remember}
                  onChange={(event) => void updateRemember(event.target.checked)}
                  disabled={submitting || consenting || !profile}
                />
                <span>{consenting ? '設定中…' : 'この会話を次の提案に使う'}</span>
              </label>
              <span className={styles.characterCount}>{message.length} / 1000</span>
              <button
                className={styles.primaryButton}
                type="submit"
                disabled={submitting || !message.trim() || context?.canSendMessage === false}
              >
                {submitting ? '聞いています…' : '送る'}
              </button>
            </div>
          </form>

          {showStarters && !context?.quickReplies.length ? (
            <div className={styles.starterRow} aria-label="入力例">
              {starters.map((starter) => (
                <button
                  key={starter}
                  type="button"
                  onClick={() => setMessage(starter)}
                  disabled={submitting}
                >
                  {starter}
                </button>
              ))}
            </div>
          ) : null}

          {error ? <InlineNotice tone="error"><p>{error}</p></InlineNotice> : null}
        </section>
      </div>
    </>
  );
}
