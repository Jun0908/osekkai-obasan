'use client';

import Image from 'next/image';
import { useEffect, useMemo, useRef, useState } from 'react';

import styles from '@/app/osekkai/osekkai.module.css';
import scenarioValue from '@/lib/osekkai/judge-demo-scenario.generated.json';
import type { JudgeDemoScenario } from '@/lib/osekkai/types.generated';

const scenario = scenarioValue as JudgeDemoScenario;

type ReplayItem = {
  choice: JudgeDemoScenario['stories'][number]['steps'][number]['choices'][number];
  selectedEventId: string | null;
};

function formatEventDate(value: string): string {
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric',
    day: 'numeric',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Asia/Tokyo',
  }).format(new Date(value));
}

function routeLabel(route: JudgeDemoScenario['events'][number]['route']): string {
  if (!route) return '経路未記録';
  return `記録済み ${route.mode === 'walk' ? '徒歩' : '公共交通'}${route.minutes}分`;
}

export default function JudgeDemoClient() {
  const [storyIndex, setStoryIndex] = useState(0);
  const [scene, setScene] = useState(0);
  const [selectionIndexes, setSelectionIndexes] = useState<number[]>([]);
  const messagesRef = useRef<HTMLDivElement>(null);
  const story = scenario.stories[storyIndex];
  const completed = scene >= story.steps.length;
  const currentStep = completed ? null : story.steps[scene];
  const progress = Math.round((scene / story.steps.length) * 100);

  const replay = useMemo(() => {
    let currentOrder: string[] = [];
    let firstOrder: string[] = [];
    let selectedEventId: string | null = null;
    let orderChanges = 0;
    const items: ReplayItem[] = [];

    selectionIndexes.forEach((choiceIndex, stepIndex) => {
      const choice = story.steps[stepIndex]?.choices[choiceIndex];
      if (!choice) return;
      if (choice.eventOrder.length > 0) {
        const nextOrder = [...choice.eventOrder];
        if (firstOrder.length === 0) firstOrder = nextOrder;
        if (currentOrder.length > 0 && currentOrder.join('|') !== nextOrder.join('|')) orderChanges += 1;
        currentOrder = nextOrder;
      }
      if (choice.selectFirstEvent) selectedEventId = currentOrder[0] ?? null;
      items.push({ choice, selectedEventId: choice.selectFirstEvent ? selectedEventId : null });
    });

    return { currentOrder, firstOrder, items, orderChanges, selectedEventId };
  }, [selectionIndexes, story]);

  const eventById = useMemo(
    () => new Map(scenario.events.map((event) => [event.id, event])),
    [],
  );
  const orderedEvents = replay.currentOrder
    .map((eventId) => eventById.get(eventId))
    .filter((event): event is JudgeDemoScenario['events'][number] => Boolean(event));

  useEffect(() => {
    const messages = messagesRef.current;
    if (messages) messages.scrollTop = messages.scrollHeight;
  }, [scene, storyIndex]);

  function resetStory(nextStoryIndex = storyIndex) {
    setStoryIndex(nextStoryIndex);
    setScene(0);
    setSelectionIndexes([]);
  }

  function choose(choiceIndex: number) {
    setSelectionIndexes((current) => [...current, choiceIndex]);
    setScene((current) => current + 1);
  }

  function actionLabel(choice: NonNullable<typeof currentStep>['choices'][number]): string {
    if (choice.selectFirstEvent && choice.label === '1番目に行ってみる' && orderedEvents[0]) {
      return `${orderedEvents[0].title}に行ってみる`;
    }
    return choice.label;
  }

  return (
    <div className={styles.judgeDemoPage}>
      <section className={styles.judgeDemoHero}>
        <div className={styles.judgeDemoHeroCopy}>
          <div className={styles.judgeDemoBadges}>
            <span>Googleログイン不要</span>
            <span>Backendなしで再現</span>
            <span>3 Story</span>
          </div>
          <p className={styles.eyebrow}>OSEKKAI JUDGE DEMO</p>
          <h1>押すだけじゃない。<br />距離を学ぶ<br />おせっかい。</h1>
          <p>
            空いた日に誘う。疲れた日は引く。参加できたら、次も会える場所へつなぐ。おばさんの距離感が変わる3つの場面を、ログインなしで再現します。
          </p>
          <div className={styles.judgeDemoContext} aria-label="選択中Storyの前提">
            <div><small>覚えていること</small><strong>{story.persona.rememberedPreferences.join('・')}</strong></div>
            <div><small>Calendar</small><strong>{story.calendarLabel}</strong></div>
            <div><small>Demo data</small><strong>実Event snapshot＋合成FreeBusy</strong></div>
          </div>
        </div>
        <div className={styles.judgeDemoHeroVisual}>
          <Image
            src="/osekkai/osekkai-obasan-logo-v1.png"
            alt="スマートフォンで交流Eventを提案する、おっせかいおばさん"
            width={440}
            height={440}
            priority
          />
        </div>
      </section>

      <nav className={styles.judgeDemoStorySelector} aria-label="Demo Storyを選ぶ">
        {scenario.stories.map((item, index) => (
          <button
            aria-current={index === storyIndex ? 'true' : undefined}
            data-active={index === storyIndex}
            key={item.id}
            onClick={() => resetStory(index)}
            type="button"
          >
            <span>STORY {item.storyNumber} · {item.kicker}</span>
            <strong>{item.title}</strong>
            <small>{item.summary}</small>
          </button>
        ))}
      </nav>

      <section className={styles.judgeDemoStory} aria-labelledby="judge-demo-story-heading">
        <header className={styles.judgeDemoStoryHeader}>
          <div>
            <p className={styles.eyebrow}>STORY {story.storyNumber} · {story.kicker}</p>
            <h2 id="judge-demo-story-heading">{story.title}</h2>
            <p className={styles.judgeDemoJudgePoint}>{story.judgePoint}</p>
          </div>
          <div className={styles.judgeDemoProgressMeta}>
            <span>{completed ? '完了' : `Scene ${scene + 1} / ${story.steps.length}`}</span>
            <button type="button" onClick={() => resetStory()} disabled={scene === 0}>最初から見る</button>
          </div>
          <div
            className={styles.judgeDemoProgress}
            role="progressbar"
            aria-label={`Story ${story.storyNumber}の進捗`}
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
          >
            <span style={{ width: `${progress}%` }} />
          </div>
        </header>

        <div className={styles.judgeDemoGrid}>
          <div className={styles.judgeDemoConversation} aria-live="polite">
            <div className={styles.judgeDemoChatHeader}>
              <div className={styles.judgeDemoAvatar}>
                <Image src="/osekkai/osekkai-obasan-logo-v1.png" alt="" width={56} height={56} />
              </div>
              <div><strong>おっせかいおばさん</strong><small>ログイン不要の審査用再現</small></div>
              <span>DEMO</span>
            </div>

            <div className={styles.judgeDemoMessages} ref={messagesRef}>
              <div className={styles.judgeDemoAgentMessage}><p>{story.openingReply}</p></div>

              {replay.items.map(({ choice, selectedEventId }, index) => {
                const selectedEvent = selectedEventId ? eventById.get(selectedEventId) : null;
                const userMessage = choice.userMessage
                  ?? (selectedEvent ? `${selectedEvent.title}に行ってみる。` : null);
                return (
                  <div className={styles.judgeDemoReplayGroup} key={`${story.id}-${index}-${choice.id}`}>
                    {choice.timeJumpLabel ? (
                      <div className={styles.judgeDemoTimeJump}><span>{choice.timeJumpLabel}</span></div>
                    ) : null}
                    {userMessage ? <div className={styles.judgeDemoUserMessage}><p>{userMessage}</p></div> : null}
                    {choice.understandingLabel ? (
                      <div className={styles.judgeDemoUnderstanding}>
                        <small>UNDERSTANDING</small><strong>{choice.understandingLabel}</strong>
                      </div>
                    ) : null}
                    <div className={styles.judgeDemoAgentMessage}><p>{choice.agentReply}</p></div>
                    {choice.memoryOutcome ? (
                      <div className={styles.judgeDemoMemoryResult}>
                        <small>NEXT MEMORY</small>
                        <strong>次の距離感が変わりました</strong>
                        <p>{choice.memoryOutcome}</p>
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>

            <div className={styles.judgeDemoActionBar}>
              {currentStep ? (
                <div className={styles.judgeDemoChoices}>
                  {currentStep.choices.map((choice, choiceIndex) => (
                    <button key={choice.id} type="button" onClick={() => choose(choiceIndex)}>
                      {actionLabel(choice)}
                    </button>
                  ))}
                </div>
              ) : (
                <div className={styles.judgeDemoCompleteActions}>
                  <button type="button" onClick={() => resetStory()}>もう一度見る</button>
                  <button type="button" onClick={() => resetStory((storyIndex + 1) % scenario.stories.length)}>
                    {storyIndex === scenario.stories.length - 1 ? 'Story 1へ' : '次のStoryへ'}
                  </button>
                </div>
              )}
              <small>API・Googleログイン不要。操作内容は端末にも保存しません。</small>
            </div>
          </div>

          <aside className={styles.judgeDemoCandidates} aria-label="審査用Event候補">
            <div className={styles.judgeDemoCandidateHeading}>
              <div><small>RECOMMENDATION DECISION</small><h2>{story.candidateTitle}</h2></div>
              <span>{orderedEvents.length > 0 ? `${orderedEvents.length} candidates` : '提案なし'}</span>
            </div>

            {orderedEvents.length > 0 ? (
              <div className={styles.judgeDemoEventList} data-adjusted={replay.orderChanges > 0}>
                {orderedEvents.map((event, index) => {
                  const initialIndex = replay.firstOrder.indexOf(event.id);
                  const selected = event.id === replay.selectedEventId;
                  const changed = replay.orderChanges > 0 && initialIndex !== index;
                  return (
                    <article
                      className={styles.judgeDemoEventCard}
                      data-selected={selected}
                      data-testid="judge-demo-event"
                      key={event.id}
                    >
                      <div className={styles.judgeDemoEventTopline}>
                        <span>#{index + 1}</span>
                        <div>{changed ? <b>順位変更</b> : null}{selected ? <b>選択</b> : null}</div>
                      </div>
                      <p>{event.providerLabel} · 記録snapshot</p>
                      <h3>{event.title}</h3>
                      <p className={styles.judgeDemoFitReason}>
                        {changed ? event.adjustedReason : event.fitReason}
                      </p>
                      <dl>
                        <div><dt>日時</dt><dd>{formatEventDate(event.startsAt)}</dd></div>
                        <div><dt>場所</dt><dd>{event.areaLabel}</dd></div>
                        <div><dt>移動</dt><dd>{routeLabel(event.route)}</dd></div>
                        <div><dt>料金</dt><dd>{event.priceLabel}</dd></div>
                      </dl>
                      <div className={styles.judgeDemoConnection}>
                        <small>交流の入口</small><strong>{event.connectionLabel}</strong>
                        <p>{event.connectionEvidence}</p>
                      </div>
                      <a href={event.sourceUrl} target="_blank" rel="noreferrer">記録に使ったSource</a>
                    </article>
                  );
                })}
              </div>
            ) : (
              <div className={styles.judgeDemoCandidatePlaceholder}>
                <strong>{story.candidateEmptyTitle}</strong>
                <p>{story.candidateEmptyDetail}</p>
              </div>
            )}
          </aside>
        </div>

        {completed ? (
          <footer className={styles.judgeDemoClosing}>
            <small>OSEKKAI OBASAN · STORY {story.storyNumber}</small>
            <strong>{story.closingLine}</strong>
          </footer>
        ) : null}
      </section>

      <details className={styles.judgeDemoDisclosure}>
        <summary>Demoデータについて</summary>
        <p>{scenario.snapshotNotice}</p>
        <div>
          {scenario.dataNotes.map((note) => (
            <section key={note.label}>
              <span>{note.label}</span>
              <strong>{note.classification}</strong>
              <p>{note.detail}</p>
            </section>
          ))}
        </div>
      </details>
    </div>
  );
}
