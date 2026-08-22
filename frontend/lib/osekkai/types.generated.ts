/* Generated from /contracts/osekkai by scripts/generate-osekkai-contracts.mjs. Do not edit. */

export interface OsekkaiContractDependencies {
inferredPreference: InferredPreference
fieldProvenance: FieldProvenance
freeWindow: FreeWindow
}
export interface InferredPreference {
value: any
confidence: number
evidence: {
id: string
text: string
createdAt: string
}[]
}
export interface FieldProvenance {
classification: ("source_snapshot" | "source_verified" | "organizer_verified" | "ai_derived" | "synthetic_demo")
sourceUrl?: string
capturedAt?: string
confidence?: number
evidenceField?: string
evidence?: string
}
export interface FreeWindow {
id: string
start: string
end: string
durationMinutes: number
verificationStatus: ("synthetic_demo" | "source_verified")
suggestedVisitStart?: string
suggestedVisitEnd?: string
}

export interface DistanceProfile {
schemaVersion: "1.0"
id: string
userId: string
memoryConsent: boolean
pushConsent: boolean
quietHours: {
start: string
end: string
timezone: "Asia/Tokyo"
}
maxPushesPerWeek: number
preferredTone: ("gentle" | "casual" | "direct" | "quiet")
maxTravelMinutes: number
maxBudgetYen: number
socialBattery: (number | null)
maxSocialIntensity: number
preferredCategories: string[]
avoidedCategories: string[]
rejectionStreak: number
cooldownUntil: (string | null)
pauseUntil: (string | null)
lastPushAt: (string | null)
explicitPreferences: {
[k: string]: any
}
inferredPreferences: {
[k: string]: InferredPreference
}
currentSignals: {
interventionHint: ("none" | "do_not_push" | "consider_push")
currentReceptivity: (number | null)
safety: {
level: ("normal" | "urgent")
requiresHumanSupport: boolean
}
observedAt: (string | null)
}
createdAt: string
updatedAt: string
}

export interface ConversationTurn {
schemaVersion: "1.0"
id: string
userId: string
role: ("user" | "assistant")
text: string
remember: boolean
createdAt: string
}

export interface ChatResult {
schemaVersion: "1.0"
reply: string
profileDelta: {
[k: string]: any
}
interventionHint: ("none" | "do_not_push" | "consider_push")
confidence: number
safety: {
requiresHumanSupport: boolean
level: ("normal" | "urgent")
message: (string | null)
supportResourcesVerified: boolean
}
persisted: boolean
conversationId: (string | null)
profile: DistanceProfile
}

export interface FreeBusyResult {
schemaVersion: "1.0"
dataMode: ("demo" | "live")
generatedAt: string
source: {
type: ("synthetic_demo" | "google_freebusy")
notice: string
}
freeWindows: FreeWindow[]
}

export interface Opportunity {
schemaVersion: "1.0"
id: string
sourceRecordId?: string
title: string
description?: string
startsAt: string
endsAt: string
address: string
latitude?: number
longitude?: number
priceYen: number
socialIntensity: number
conversationRequired: ("none" | "low" | "medium" | "high")
soloFriendly: boolean
recurring?: boolean
flexibleVisit?: boolean
visitDurationMinutes?: number
roleAvailable?: (boolean | null)
roleDescription?: (string | null)
categories?: string[]
provider: string
sourceType: ("open_data" | "organizer_verified" | "ai_derived")
sourceUrl: string
datasetUrl?: string
sourceDataset: string
license: string
capturedAt: string
checksum: string
sourceTrust?: number
confidence?: number
dataMode: ("demo" | "live")
verificationStatus: ("synthetic_demo" | "source_snapshot" | "source_verified" | "organizer_verified" | "unverified")
fieldProvenance: {
[k: string]: FieldProvenance
}
travelEstimate: {
mode: ("walk" | "transit" | "bicycle")
minutes: number
source: ("synthetic_demo" | "maps_verified")
}
}

export interface DecisionResult {
schemaVersion: "1.0"
episodeId: string
policyVersion: string
decision: ("do_not_push" | "check_in_only" | "suggest_solo_place" | "suggest_light_social" | "suggest_small_role")
shouldPush: boolean
reasonCodes: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
score: (number | null)
selectedOpportunity: (Opportunity | null)
excludedCandidates: {
opportunityId: string
reasonCodes: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
}[]
notification: ({
text: string
tone: ("gentle" | "casual" | "direct" | "quiet")
} | null)
dataMode: ("demo" | "live")
createdAt: string
}

export interface InterventionEpisode {
schemaVersion: "1.0"
id: string
userId: string
sequence: number
policyVersion: string
decision: ("do_not_push" | "check_in_only" | "suggest_solo_place" | "suggest_light_social" | "suggest_small_role")
shouldPush: boolean
reasonCodes: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
score: (number | null)
profileSnapshot: (DistanceProfile | null)
freeWindowSnapshot: (FreeWindow | null)
candidateIdsBeforeFilter: string[]
candidateIdsAfterFilter: string[]
excludedCandidates: {
opportunityId: string
reasonCodes: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
}[]
selectedOpportunity: (Opportunity | null)
notification: ({
text: string
tone: ("gentle" | "casual" | "direct" | "quiet")
shownOpportunityIds: string[]
} | null)
pushedAt: (string | null)
noPushAt: (string | null)
actionResponse: ("accepted" | "declined" | "show_another" | "pause_one_week" | null)
actionResponseAt: (string | null)
distanceFeedback: ("too_much" | "just_right" | "push_more" | null)
distanceFeedbackAt: (string | null)
attendedAt: (string | null)
revisitedAt: (string | null)
selfInitiatedAt: (string | null)
dataMode: ("demo" | "live")
metricClassification: ("measured" | "reference_estimate" | "demo" | "unverified")
minimalRecord: boolean
createdAt: string
updatedAt: string
}

export interface MetricsResult {
schemaVersion: "1.0"
generatedAt: string
dataMode: ("demo" | "live")
metrics: {
key: ("just_right_push_rate" | "overreach_rate" | "under_support_rate" | "acceptance_rate" | "attendance_rate" | "revisit_rate")
label: string
value: (number | null)
numerator: number
denominator: number
classification: ("measured" | "reference_estimate" | "demo" | "unverified")
note: string
}[]
unverifiedMetrics: {
key: string
label: string
value: null
classification: "unverified"
note: string
}[]
}

export interface ChatRequest {
message: string
remember?: boolean
}

export interface ProfileUpdateRequest {
patch?: {
memoryConsent?: boolean
pushConsent?: boolean
quietHours?: {
start: string
end: string
timezone: "Asia/Tokyo"
}
maxPushesPerWeek?: number
preferredTone?: ("gentle" | "casual" | "direct" | "quiet")
maxTravelMinutes?: number
maxBudgetYen?: number
maxSocialIntensity?: number
/**
 * @maxItems 50
 */
preferredCategories?: string[]
/**
 * @maxItems 50
 */
avoidedCategories?: string[]
}
removeEvidenceId?: string
removeInferredPreferenceKey?: string
pauseOneWeek?: true
}

export type FeedbackRequest = ({
episodeId: string
actionResponse: ("accepted" | "declined" | "show_another" | "pause_one_week")
} | {
episodeId: string
distanceFeedback: ("too_much" | "just_right" | "push_more")
})

export type InterventionRecordRequest = ({
action: "record"
episodeId: string
eventType: ("attendance" | "attended" | "revisit" | "revisited" | "selfInitiated" | "self_initiated")
status?: ("attended" | "revisited" | "self_initiated" | "recorded")
} | {
action: "record"
episodeId: string
outcome: ("attendance" | "attended" | "revisit" | "revisited" | "selfInitiated" | "self_initiated")
status?: ("attended" | "revisited" | "self_initiated" | "recorded")
})

export interface DecideRequest {

}

export interface DemoResetRequest {

}

export interface ProfileDeleteRequest {
confirm: true
}

export type SchemaVersion = "1.0";
export type DataMode = "demo" | "live";
export type MetricClassification = "measured" | "reference_estimate" | "demo" | "unverified";
export type SocialIntensity = 0 | 1 | 2 | 3 | 4 | 5;
export type PushTone = "gentle" | "casual" | "direct" | "quiet";
export type ReasonCode = "NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET";
export type DecisionType = "do_not_push" | "check_in_only" | "suggest_solo_place" | "suggest_light_social" | "suggest_small_role";
export type ActionResponse = "accepted" | "declined" | "show_another" | "pause_one_week";
export type DistanceFeedback = "too_much" | "just_right" | "push_more";
export type MeasuredMetricKey = "just_right_push_rate" | "overreach_rate" | "under_support_rate" | "acceptance_rate" | "attendance_rate" | "revisit_rate";
export type InferredEvidence = InferredPreference['evidence'][number];
export type CurrentSignals = DistanceProfile['currentSignals'];
export type SafetyResult = ChatResult['safety'];
export type FreeBusySource = FreeBusyResult['source'];
export type TravelEstimate = Opportunity['travelEstimate'];
export type ExcludedCandidate = DecisionResult['excludedCandidates'][number];
export type EpisodeNotification = NonNullable<InterventionEpisode['notification']>;
export type SelectedFreeWindow = NonNullable<InterventionEpisode['freeWindowSnapshot']>;
export type Metric = MetricsResult['metrics'][number];
export type UnverifiedMetric = MetricsResult['unverifiedMetrics'][number];
