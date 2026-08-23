'use client';

import {
  clearOsekkaiSession,
  getOsekkaiSession,
  osekkaiRequest,
  type JsonObject,
} from '@/components/osekkai/api-client';

import type {
  ActionResponse,
  ChatResult,
  DistanceFeedback,
  DistanceProfile,
  FreeBusyResult,
  MetricsResult,
  EventRouteResult,
  MapEventsResult,
} from './types.generated';
import type {
  DecideResponse,
  DemoResetResponse,
  FeedbackResponse,
  EventMeshResult,
  InterventionsResult,
  OpportunitiesResult,
  ProfileDeleteResponse,
  RecordOutcomeResponse,
  SourceStatusResult,
  SessionResult,
} from './types';

/**
 * Typed facade over the one canonical browser transport implementation.
 * Session caching, CSRF, idempotency, envelope parsing, and runtime response
 * validation all remain in components/osekkai/api-client.ts.
 */
export const osekkaiApi = {
  session: () => getOsekkaiSession() as Promise<SessionResult>,
  profile: () => osekkaiRequest<DistanceProfile>('/profile'),
  updateProfile: (patch: JsonObject) =>
    osekkaiRequest<DistanceProfile>('/profile', {
      method: 'PATCH',
      mutation: true,
      body: patch,
    }),
  deleteProfile: () =>
    osekkaiRequest<ProfileDeleteResponse>('/profile', {
      method: 'DELETE',
      mutation: true,
      body: { confirm: true },
    }).finally(clearOsekkaiSession),
  chat: (text: string, remember: boolean) =>
    osekkaiRequest<ChatResult>('/chat', {
      method: 'POST',
      mutation: true,
      body: { message: text, remember },
    }),
  freebusy: () => osekkaiRequest<FreeBusyResult>('/freebusy'),
  opportunities: () => osekkaiRequest<OpportunitiesResult>('/opportunities'),
  eventRoute: (eventId: string, latitude: number, longitude: number) =>
    osekkaiRequest<EventRouteResult>('/routes', {
      method: 'POST',
      mutation: true,
      body: { eventId, origin: { latitude, longitude } },
    }),
  events: () => osekkaiRequest<EventMeshResult>('/events'),
  mapEvents: (offset = 0, limit = 250) =>
    osekkaiRequest<MapEventsResult>(`/map-events?offset=${offset}&limit=${limit}`),
  sources: () => osekkaiRequest<SourceStatusResult>('/sources'),
  syncSources: (force = false) =>
    osekkaiRequest<SourceStatusResult>('/sources', {
      method: 'POST',
      mutation: true,
      body: { force },
    }),
  decide: () =>
    osekkaiRequest<DecideResponse>('/decide', {
      method: 'POST',
      mutation: true,
      body: {},
    }),
  interventions: () => osekkaiRequest<InterventionsResult>('/interventions'),
  recordOutcome: (
    episodeId: string,
    outcome: 'attended' | 'revisited' | 'self_initiated',
  ) =>
    osekkaiRequest<RecordOutcomeResponse>('/interventions', {
      method: 'POST',
      mutation: true,
      body: { episodeId, outcome },
    }),
  feedback: (
    episodeId: string,
    feedback: { actionResponse?: ActionResponse; distanceFeedback?: DistanceFeedback },
  ) =>
    osekkaiRequest<FeedbackResponse>('/feedback', {
      method: 'POST',
      mutation: true,
      body: { episodeId, ...feedback },
    }),
  metrics: () => osekkaiRequest<MetricsResult>('/metrics'),
  resetDemo: () =>
    osekkaiRequest<DemoResetResponse>('/demo/reset', {
      method: 'POST',
      mutation: true,
      body: {},
    }),
};

export function resetOsekkaiClientSessionForTests(): void {
  clearOsekkaiSession();
}
