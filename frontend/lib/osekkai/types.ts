export * from "./types.generated";

import type {
  DataMode,
  DecisionResult,
  DistanceProfile,
  FreeBusyResult,
  InterventionEpisode,
  MetricsResult,
  Opportunity,
  LiveEvent
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

export interface SourceRuntimeStatus {
  id: string;
  displayName: string;
  requiredForDemo: boolean;
  readiness: string;
  health: string;
  lastAttemptAt: string | null;
  lastSuccessAt: string | null;
  eventCount: number;
  datasetCount: number;
  error: string | null;
  stale: boolean;
  refreshMinutes: number;
}

export interface SourceStatusResult {
  schemaVersion: "1.0";
  dataMode: "live";
  generatedAt: string;
  sources: SourceRuntimeStatus[];
  counts: { events: number; eligibleEvents: number; opportunities: number; providerErrors: number };
}

export interface EventMeshResult {
  schemaVersion: "1.0";
  dataMode: "live";
  generatedAt: string;
  events: LiveEvent[];
  eligibleEvents: LiveEvent[];
  excludedEvents: Array<{ eventId?: string; provider?: string; reasons: string[] }>;
  series: unknown[];
  communities: unknown[];
  providerErrors: unknown[];
  connectionEvidence: unknown[];
  routeErrors: unknown[];
  routeCount: number;
  opportunityExclusions: unknown[];
  counts: { received: number; merged: number; eligible: number; excluded: number };
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
