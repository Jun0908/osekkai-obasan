export * from "./types.generated";

import type {
  DataMode,
  DecisionResult,
  DistanceProfile,
  FreeBusyResult,
  InterventionEpisode,
  MetricsResult,
  Opportunity
} from "./types.generated";

export interface SessionResult {
  csrfToken: string;
  expiresAt: string;
  dataMode: DataMode;
}

export interface OpportunitiesResult {
  schemaVersion: "1.0";
  dataMode: DataMode;
  notice: string;
  opportunities: Opportunity[];
}

export interface InterventionsResult {
  schemaVersion: "1.0";
  interventions: InterventionEpisode[];
}

export interface DecideResponse {
  decision: DecisionResult;
  episode: InterventionEpisode;
}

export interface FeedbackResponse {
  episode: InterventionEpisode;
  profile: DistanceProfile;
  alternativeOpportunity: Opportunity | null;
  message: string | null;
}

export interface RecordOutcomeResponse {
  episode: InterventionEpisode;
  recordedOutcome: "attended" | "revisited" | "self_initiated";
}

export interface ProfileDeleteResponse {
  schemaVersion: "1.0";
  deleted: true;
  deletedCounts: Record<string, number>;
}

export interface DemoResetResponse {
  schemaVersion: "1.0";
  dataMode: "demo";
  resetAt: string;
  deleted: Record<string, number>;
  profile: DistanceProfile;
  freebusy: FreeBusyResult;
  opportunities: OpportunitiesResult;
  interventions: InterventionsResult;
  metrics: MetricsResult;
}

export interface OsekkaiState {
  dataMode: DataMode;
  profile: DistanceProfile;
  freebusy: FreeBusyResult;
  opportunities: OpportunitiesResult;
  interventions: InterventionsResult;
  metrics: MetricsResult;
}
