import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiMocks = vi.hoisted(() => ({
  clearOsekkaiSession: vi.fn(),
  getOsekkaiSession: vi.fn(),
  osekkaiRequest: vi.fn(),
}));
const navigationMocks = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock('./api-client', () => ({
  clearOsekkaiSession: apiMocks.clearOsekkaiSession,
  friendlyApiError: (error: unknown) => error instanceof Error ? error.message : String(error),
  getOsekkaiSession: apiMocks.getOsekkaiSession,
  newIdempotencyKey: (prefix: string) => `${prefix}-test-id`,
  osekkaiRequest: apiMocks.osekkaiRequest,
}));
vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: navigationMocks.push }),
}));

import ChatClient from './chat-client';
import DemoClient from './demo-client';
import ImpactClient from './impact-client';
import SettingsClient from './settings-client';

const profile = {
  memoryConsent: true,
  pushConsent: false,
  quietHours: { start: '21:00', end: '08:00', timezone: 'Asia/Tokyo' },
  maxPushesPerWeek: 2,
  preferredTone: 'gentle',
  maxTravelMinutes: 30,
  maxBudgetYen: 2000,
  maxSocialIntensity: 2,
  socialBattery: 24,
  rejectionStreak: 0,
  inferredPreferences: {
    conversationPreference: {
      value: '静かな会話',
      confidence: 0.9,
      evidence: [
        { id: 'evidence-1', text: '大人数は疲れる', createdAt: '2026-08-20T10:00:00+09:00' },
        { id: 'evidence-2', text: '話さずに過ごしたい', createdAt: '2026-08-21T10:00:00+09:00' },
      ],
    },
  },
};

function chatResult(
  state = 'getting_to_know',
  overrides: Record<string, unknown> = {},
) {
  return {
    schemaVersion: '1.0',
    reply: 'あんた、何が好きなのよ。最近やってみたいこと、ひとつ教えて。',
    profileDelta: {},
    frictionDelta: [],
    interventionHint: 'none',
    confidence: 1,
    safety: {
      requiresHumanSupport: false,
      level: 'normal',
      message: null,
      supportResourcesVerified: false,
    },
    persisted: false,
    conversationId: null,
    profile,
    context: {
      schemaVersion: '1.0',
      episodeId: '33333333-3333-4333-8333-333333333333',
      state,
      trigger: 'user_initiated',
      quickReplies: [],
      recommendations: [],
      calendarSummary: null,
      selectedOpportunityId: null,
      checkInDueAt: null,
      canSendMessage: true,
      notice: null,
    },
    ...overrides,
  };
}

describe('Osekkai client components', () => {
  beforeEach(() => {
    apiMocks.getOsekkaiSession.mockResolvedValue({
      csrfToken: 'csrf-test-token',
      dataMode: 'demo',
      expiresAt: '2026-08-22T12:00:00+09:00',
    });
    apiMocks.osekkaiRequest.mockReset();
    apiMocks.clearOsekkaiSession.mockReset();
    navigationMocks.push.mockReset();
  });

  it('Chat asks one hobby question without exposing internal profile panels', async () => {
    apiMocks.osekkaiRequest.mockImplementation(async (path: string) => {
      if (path === '/profile') return profile;
      if (path === '/chat') return chatResult();
      throw new Error(`unexpected path: ${path}`);
    });

    render(<ChatClient />);

    expect(await screen.findByText('あんた、何が好きなのよ。最近やってみたいこと、ひとつ教えて。')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'おばさんに話す' })).toBeInTheDocument();
    expect(screen.getByText('ヨガをやってみたい')).toBeInTheDocument();
    expect(screen.getByText('ボルダリングが好き')).toBeInTheDocument();
    expect(screen.queryByText(/大人数は疲れる/)).not.toBeInTheDocument();
    expect(screen.queryByText('Memory')).not.toBeInTheDocument();
    expect(screen.queryByText('Why')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'ボルダリングが好き' }));
    expect(screen.getByRole('textbox', { name: '好きなこと、ひっかかること、行ったあとの感想' }))
      .toHaveValue('ボルダリングが好き');
  });

  it('Settings keeps learned preferences private until opened and deletes selected evidence', async () => {
    apiMocks.osekkaiRequest.mockImplementation(async (path: string) => {
      if (path === '/profile') return profile;
      throw new Error(`unexpected path: ${path}`);
    });

    render(<SettingsClient />);

    const disclosure = await screen.findByText('保存された好みを確認・削除');
    expect(screen.queryByText(/大人数は疲れる/)).not.toBeVisible();
    fireEvent.click(disclosure);
    expect(screen.getByText(/大人数は疲れる/)).toBeVisible();
    expect(screen.getByText(/話さずに過ごしたい/)).toBeVisible();

    fireEvent.click(screen.getByRole('button', {
      name: '会話の少なさの根拠「話さずに過ごしたい」を削除',
    }));

    await waitFor(() => {
      expect(apiMocks.osekkaiRequest).toHaveBeenCalledWith('/profile', {
        method: 'PATCH',
        mutation: true,
        body: {
          removeEvidenceId: 'evidence-2',
          idempotencyKey: 'evidence-delete-test-id',
        },
      });
    });
    expect(apiMocks.osekkaiRequest).not.toHaveBeenCalledWith(
      '/profile',
      expect.objectContaining({
        body: expect.objectContaining({ operation: 'remove_inferred_preference' }),
      }),
    );
  });

  it('Chat keeps shortlist, one friction question, adjustment, and selection in one screen', async () => {
    const opportunity = {
      id: 'opportunity-1',
      title: '初心者ボルダリング交流会',
      startsAt: '2026-09-05T13:00:00+09:00',
      endsAt: '2026-09-05T15:00:00+09:00',
      address: '東京都内',
      provider: 'Lu.ma',
      sourceUrl: 'https://lu.ma/example',
      sourceClassification: 'live_provider',
      capturedAt: '2026-08-23T10:00:00+09:00',
      revalidatedAt: '2026-08-23T10:00:00+09:00',
      travelEstimate: { minutes: 18 },
      priceYen: 1000,
      registrationStatus: 'open',
    };
    const recommendations = [{
      rank: 1,
      opportunity,
      recommendationReasons: [{
        code: 'personal_fit',
        text: '好みと空き時間に合う候補です。',
        evidenceUrl: opportunity.sourceUrl,
        classification: 'private_user_data',
      }],
    }];
    apiMocks.osekkaiRequest.mockImplementation(async (
      path: string,
      options?: { method?: string; body?: Record<string, unknown> },
    ) => {
      if (path === '/profile') return profile;
      if (path === '/chat' && options?.body?.action === 'start') return chatResult();
      if (path === '/chat' && options?.body?.action === 'select') {
        return chatResult('accepted', {
          reply: 'よし、決まり。終わったあとに一言だけ聞くわ。',
          context: {
            ...chatResult().context,
            state: 'accepted',
            selectedOpportunityId: opportunity.id,
            checkInDueAt: '2026-09-05T17:00:00+09:00',
          },
        });
      }
      if (path === '/chat' && options?.body?.message === 'これは違う') {
        return chatResult('friction_probe', {
          reply: '何がひっかかった？ 一つだけ教えて。',
          context: {
            ...chatResult().context,
            state: 'friction_probe',
            quickReplies: [
              { id: 'first-time', label: '初参加が不安', message: '初参加で入り方がわからない' },
            ],
          },
        });
      }
      if (path === '/chat' && options?.body?.message === '初参加で入り方がわからない') {
        return chatResult('adjusted_shortlist', {
          reply: '初参加しやすい条件で一回だけ並べ直したで。',
          context: {
            ...chatResult().context,
            state: 'adjusted_shortlist',
            recommendations,
          },
        });
      }
      if (path === '/chat') {
        return chatResult('shortlist_shown', {
          reply: '空き時間と移動まで見て候補を持ってきたで。',
          context: {
            ...chatResult().context,
            state: 'shortlist_shown',
            recommendations,
          },
        });
      }
      throw new Error(`unexpected path: ${path}`);
    });

    render(<ChatClient />);
    const composer = await screen.findByRole('textbox', { name: '好きなこと、ひっかかること、行ったあとの感想' });
    fireEvent.change(composer, { target: { value: 'ボルダリングが好き' } });
    fireEvent.click(screen.getByRole('button', { name: '送る' }));
    fireEvent.click(await screen.findByRole('button', { name: 'これは違う' }));
    fireEvent.click(await screen.findByRole('button', { name: '初参加が不安' }));
    fireEvent.click(await screen.findByRole('button', { name: '行ってみる' }));

    await waitFor(() => {
      expect(apiMocks.osekkaiRequest).toHaveBeenCalledWith('/chat', {
        method: 'POST',
        mutation: true,
        body: expect.objectContaining({
          action: 'select',
          opportunityId: opportunity.id,
        }),
      });
      expect(screen.getByText(/よし、決まり/)).toBeInTheDocument();
    });
  });

  it('Settings keeps memory and push consent independent and requires the exact delete word', async () => {
    apiMocks.osekkaiRequest.mockResolvedValue(profile);

    render(<SettingsClient />);

    const memorySwitch = await screen.findByRole('switch', {
      name: /会話から距離感を学んでよい/,
    });
    const pushSwitch = screen.getByRole('switch', {
      name: /条件が合うとき、声をかけてよい/,
    });

    expect(memorySwitch).toBeChecked();
    expect(pushSwitch).not.toBeChecked();
    expect(memorySwitch).not.toBe(pushSwitch);

    fireEvent.click(screen.getByRole('button', { name: 'すべての記憶と履歴を削除' }));
    const confirmation = screen.getByRole('group', { name: 'この操作は元に戻せません' });
    expect(within(confirmation).getByText('確認のため「削除」と入力')).toBeInTheDocument();

    const deleteInput = within(confirmation).getByRole('textbox', {
      name: '確認のため「削除」と入力',
    });
    const completeDelete = within(confirmation).getByRole('button', { name: '完全に削除する' });
    expect(completeDelete).toBeDisabled();

    fireEvent.change(deleteInput, { target: { value: '消去' } });
    expect(completeDelete).toBeDisabled();
    fireEvent.change(deleteInput, { target: { value: '削除' } });
    expect(completeDelete).toBeEnabled();
  });

  it('Demo runs the first real step and advances progress to 1 of 12', async () => {
    let finishSeed!: () => void;
    const seedPending = new Promise<{ seeded: true }>((resolve) => {
      finishSeed = () => resolve({ seeded: true });
    });
    apiMocks.osekkaiRequest.mockImplementation(async (path: string) => {
      if (path === '/demo/seed') return seedPending;
      if (path === '/chat') {
        return {
          reply: '疲れた気持ちを受け取りました。',
          interventionHint: 'do_not_push',
          confidence: 0.92,
          profileDelta: {},
          safety: { requiresHumanSupport: false },
        };
      }
      throw new Error(`unexpected path: ${path}`);
    });

    render(<DemoClient />);

    expect(screen.getByText('0 / 12 完了')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '準備中…' })).toBeDisabled();
    finishSeed();
    fireEvent.click(await screen.findByRole('button', { name: '会話を送る' }));

    expect(await screen.findByText('1 / 12 完了')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'デモの進捗' })).toHaveAttribute('aria-valuenow', '1');
    expect(apiMocks.osekkaiRequest).toHaveBeenCalledWith('/chat', {
      method: 'POST',
      mutation: true,
      body: {
        message: '今週疲れた。何もしたくない',
        remember: true,
        idempotencyKey: 'demo-chat-test-id',
      },
    });
    expect(apiMocks.osekkaiRequest).toHaveBeenCalledWith('/demo/seed', {
      method: 'POST',
      mutation: true,
      body: { idempotencyKey: 'demo-seed-test-id' },
    });
  });

  it('Demo preserves mounted progress and does not initialize twice on rerender', async () => {
    apiMocks.osekkaiRequest.mockImplementation(async (path: string) => {
      if (path === '/demo/seed') return { seeded: false };
      if (path === '/chat') return { reply: '会話を記録しました。' };
      throw new Error(`unexpected path: ${path}`);
    });

    const view = render(<DemoClient />);
    fireEvent.click(await screen.findByRole('button', { name: '会話を送る' }));
    expect(await screen.findByText('1 / 12 完了')).toBeInTheDocument();

    view.rerender(<DemoClient />);
    expect(screen.getByText('1 / 12 完了')).toBeInTheDocument();
    expect(
      apiMocks.osekkaiRequest.mock.calls.filter(([path]) => path === '/demo/seed'),
    ).toHaveLength(1);
  });

  it('Demo requires an explicit destructive reset confirmation', async () => {
    apiMocks.osekkaiRequest.mockImplementation(async (path: string) => {
      if (path === '/demo/seed') return { seeded: false };
      if (path === '/demo/reset') return { resetAt: '2019-02-23T10:00:00+09:00' };
      throw new Error(`unexpected path: ${path}`);
    });

    render(<DemoClient />);
    const openReset = await screen.findByRole('button', { name: 'デモをリセット' });
    await waitFor(() => expect(openReset).toBeEnabled());
    fireEvent.click(openReset);

    const confirmation = screen.getByRole('group', {
      name: 'この匿名セッションのデータを削除します',
    });
    expect(within(confirmation).getByText(/Profile、会話、判断、フィードバック、KPI/)).toBeInTheDocument();
    const confirmReset = within(confirmation).getByRole('button', {
      name: 'データを削除してリセット',
    });
    expect(confirmReset).toBeDisabled();
    fireEvent.change(
      within(confirmation).getByRole('textbox', { name: '確認のため「リセット」と入力' }),
      { target: { value: 'リセット' } },
    );
    expect(confirmReset).toBeEnabled();
    fireEvent.click(confirmReset);

    await waitFor(() => {
      expect(apiMocks.osekkaiRequest).toHaveBeenCalledWith('/demo/reset', {
        method: 'POST',
        mutation: true,
        body: { idempotencyKey: 'demo-reset-test-id' },
      });
    });
  });

  it('Demo completes all 12 steps from a fresh session without manual reset', async () => {
    const opportunity = {
      id: '44444444-4444-4444-8444-444444444444',
      title: '静かな展示',
      provider: '公開データ',
      priceYen: 0,
      socialIntensity: 1,
      travelMinutes: 15,
    };
    let decideCount = 0;
    apiMocks.osekkaiRequest.mockImplementation(async (path: string) => {
      if (path === '/demo/seed') return { seeded: true };
      if (path === '/chat') return { reply: '気持ちを受け取りました。' };
      if (path === '/profile') return { ...profile, pushConsent: true };
      if (path === '/freebusy') {
        return {
          freeWindows: [{
            start: '2019-02-23T13:00:00+09:00',
            end: '2019-02-23T17:00:00+09:00',
            durationMinutes: 240,
          }],
        };
      }
      if (path === '/opportunities') return { opportunities: [opportunity] };
      if (path === '/decide') {
        decideCount += 1;
        return decideCount === 1
          ? {
              episode: {
                id: '55555555-5555-4555-8555-555555555555',
                decision: 'do_not_push',
                shouldPush: false,
                reasonCodes: ['EXPLICIT_NO_ACTION'],
              },
            }
          : {
              episode: {
                id: '66666666-6666-4666-8666-666666666666',
                decision: 'suggest_solo_place',
                shouldPush: true,
                reasonCodes: ['FREE_WINDOW_AVAILABLE', 'WITHIN_TRAVEL_LIMIT'],
                selectedOpportunity: opportunity,
              },
            };
      }
      if (path === '/feedback') return { recorded: true };
      if (path === '/interventions') return { recorded: true };
      if (path === '/metrics') return { metrics: [] };
      throw new Error(`unexpected path: ${path}`);
    });

    render(<DemoClient />);
    const scenario = screen.getByRole('region', { name: '中心デモ' });
    const actions = [
      '会話を送る',
      'Profileを確認',
      '判断を実行',
      '次の会話を送る',
      '空き時間を読む',
      '候補を読む',
      '判断を実行',
      '行ってみる',
      'ちょうどいい',
      '参加を記録',
      '再訪を記録',
      'KPIを更新',
    ];

    for (const [index, action] of Array.from(actions.entries())) {
      const button = await within(scenario).findByRole('button', { name: action });
      fireEvent.click(button);
      await waitFor(() => {
        expect(screen.getByText(`${index + 1} / 12 完了`)).toBeInTheDocument();
      });
    }

    expect(screen.getByText('12段階のデモが完了しました')).toBeInTheDocument();
    expect(decideCount).toBe(2);
    expect(
      apiMocks.osekkaiRequest.mock.calls.filter(([path]) => path === '/demo/seed'),
    ).toHaveLength(1);
    expect(apiMocks.osekkaiRequest).toHaveBeenCalledWith('/feedback', {
      method: 'POST',
      mutation: true,
      body: expect.objectContaining({
        episodeId: '66666666-6666-4666-8666-666666666666',
        actionResponse: 'accepted',
      }),
    });
  });

  it('Impact labels measured, demo, and unverified KPIs without inventing missing values', async () => {
    apiMocks.osekkaiRequest.mockImplementation(async (path: string) => {
      if (path === '/profile') return profile;
      if (path === '/interventions') {
        return {
          interventions: [{
            id: 'episode-1',
            sequence: 1,
            decidedAt: '2026-08-22T10:00:00+09:00',
            decision: 'suggest_solo_place',
            shouldPush: true,
            reasonCodes: ['WITHIN_TRAVEL_LIMIT'],
            metricClassification: 'demo',
            selectedOpportunity: { id: 'event-1', title: '静かな展示' },
          }],
        };
      }
      if (path === '/metrics') {
        return {
          metrics: {
            justRightPushRate: {
              value: 0.5,
              numerator: 1,
              denominator: 2,
              classification: 'measured',
            },
            pushCount: {
              value: 3,
              classification: 'demo',
            },
          },
        };
      }
      throw new Error(`unexpected path: ${path}`);
    });

    render(<ImpactClient />);

    const measuredHeading = await screen.findByRole('heading', { name: 'ちょうどいい率' });
    const measuredCard = measuredHeading.closest('article');
    expect(measuredCard).not.toBeNull();
    expect(within(measuredCard as HTMLElement).getByText('実測')).toBeInTheDocument();
    expect(within(measuredCard as HTMLElement).getByText('50%')).toBeInTheDocument();
    expect(within(measuredCard as HTMLElement).getByText('n=2')).toBeInTheDocument();

    const demoHeading = screen.getByRole('heading', { name: 'PUSH判断' });
    const demoCard = demoHeading.closest('article');
    expect(demoCard).not.toBeNull();
    expect(within(demoCard as HTMLElement).getByText('デモシナリオ')).toBeInTheDocument();
    expect(within(demoCard as HTMLElement).getByText('3')).toBeInTheDocument();

    const unverifiedHeading = screen.getByRole('heading', { name: 'Third Place獲得率' });
    const unverifiedCard = unverifiedHeading.closest('article');
    expect(unverifiedCard).not.toBeNull();
    expect(within(unverifiedCard as HTMLElement).getByText('未検証')).toBeInTheDocument();
    expect(within(unverifiedCard as HTMLElement).getByText('未計測')).toBeInTheDocument();
  });
});
