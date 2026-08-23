/* Generated from /contracts/osekkai by scripts/generate-osekkai-contracts.mjs. Do not edit. */

export interface OsekkaiContractDependencies {
inferredPreference: InferredPreference
fieldProvenance: FieldProvenance
freeWindow: FreeWindow
evidence: Evidence
source: Source
rankedOpportunity: RankedOpportunity
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
export interface Evidence {
kind: ("recurrence" | "future_occurrence" | "solo_friendly" | "beginner_friendly" | "structured_conversation" | "shared_meal" | "group_work" | "role_available" | "community_path" | "capacity" | "registration" | "personal_fit" | "risk")
text: string
url: string
classification: ("raw_open_data" | "live_provider" | "ai_derived" | "organizer_verified" | "private_user_data" | "synthetic_demo")
capturedAt: string
confidence: number
evidenceField?: (string | null)
}
export interface Source {
id: string
displayName: string
kind: ("open_data" | "live_provider" | "public_official_site" | "organizer_intake" | "deep_link")
accessMethod: ("api" | "ical" | "json_ld" | "html" | "webhook" | "manual")
baseUrl: string
termsUrl: string
license: string
attribution: string
enabled: boolean
authorized: boolean
refreshMinutes: number
staleAfterMinutes: number
credentialEnv: string[]
storagePolicy: ("normalized_only" | "metadata_and_normalized" | "ephemeral")
requiredForDemo: boolean
}
export interface RankedOpportunity {
rank: number
score: number
opportunityId: string
/**
 * @minItems 1
 */
recommendationReasons: [RecommendationReason, ...(RecommendationReason)[]]
exclusionReasons: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "CONNECTION_LEVEL" | "REGISTRATION_UNAVAILABLE" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
}
export interface RecommendationReason {
code: ("connection" | "continuity" | "solo_friendly" | "personal_fit" | "adjacent_interest" | "calendar_fit" | "travel_fit" | "budget_fit")
text: string
evidenceUrl: (string | null)
classification: ("raw_open_data" | "live_provider" | "ai_derived" | "organizer_verified" | "private_user_data" | "synthetic_demo")
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
participationFriction: ParticipationFrictionProfile
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

export interface ParticipationFrictionProfile {
[k: string]: {
value: true
origin: ("explicit" | "inferred")
confidence: number
evidence: {
id: string
referenceType: ("message" | "feedback")
referenceId: string
text: string
observedAt: string
lastConfirmedAt: string
}[]
observedAt: string
lastConfirmedAt: string
}
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

export interface ConversationEpisode {
schemaVersion: "1.0"
id: string
userId: string
state: ("getting_to_know" | "calendar_sparse" | "shortlist_shown" | "friction_probe" | "adjusted_shortlist" | "accepted" | "check_in_due" | "cooldown" | "safety_handoff")
trigger: ("user_initiated" | "calendar_sparse" | "preference_intake" | "check_in")
startedReason: string
/**
 * @maxItems 3
 */
shownOpportunityIds: []|[string]|[string, string]|[string, string, string]
/**
 * @maxItems 3
 */
adjustedOpportunityIds: []|[string]|[string, string]|[string, string, string]
presentationCount: number
adjustmentCount: number
selectedOpportunityId: (string | null)
selectedEventId: (string | null)
selectedEventEndsAt: (string | null)
checkInDueAt: (string | null)
checkInCompletedAt: (string | null)
cooldownUntil: (string | null)
frictionEvidenceIds: string[]
turnIds: string[]
closedAt: (string | null)
createdAt: string
updatedAt: string
}

export interface ConversationContext {
schemaVersion: "1.0"
episodeId: (string | null)
state: ("getting_to_know" | "calendar_sparse" | "shortlist_shown" | "friction_probe" | "adjusted_shortlist" | "accepted" | "check_in_due" | "cooldown" | "safety_handoff")
trigger: ("user_initiated" | "calendar_sparse" | "preference_intake" | "check_in")
/**
 * @maxItems 3
 */
quickReplies: []|[{
id: string
label: string
message: string
}]|[{
id: string
label: string
message: string
}, {
id: string
label: string
message: string
}]|[{
id: string
label: string
message: string
}, {
id: string
label: string
message: string
}, {
id: string
label: string
message: string
}]
/**
 * @maxItems 3
 */
recommendations: []|[{
rank: number
opportunity: Opportunity
/**
 * @minItems 1
 * @maxItems 6
 */
recommendationReasons: [RecommendationReason]|[RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]
}]|[{
rank: number
opportunity: Opportunity
/**
 * @minItems 1
 * @maxItems 6
 */
recommendationReasons: [RecommendationReason]|[RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]
}, {
rank: number
opportunity: Opportunity
/**
 * @minItems 1
 * @maxItems 6
 */
recommendationReasons: [RecommendationReason]|[RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]
}]|[{
rank: number
opportunity: Opportunity
/**
 * @minItems 1
 * @maxItems 6
 */
recommendationReasons: [RecommendationReason]|[RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]
}, {
rank: number
opportunity: Opportunity
/**
 * @minItems 1
 * @maxItems 6
 */
recommendationReasons: [RecommendationReason]|[RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]
}, {
rank: number
opportunity: Opportunity
/**
 * @minItems 1
 * @maxItems 6
 */
recommendationReasons: [RecommendationReason]|[RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]|[RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason, RecommendationReason]
}]
calendarSummary: ({
source: ("google_freebusy" | "synthetic_demo")
generatedAt: string
longFreeWindowCount: number
busyOccupancyPercent: number
} | null)
selectedOpportunityId: (string | null)
checkInDueAt: (string | null)
canSendMessage: boolean
notice: (string | null)
}

export interface ChatResult {
schemaVersion: "1.0"
reply: string
profileDelta: {
[k: string]: any
}
frictionDelta: ("search_fatigue" | "first_time_anxiety" | "stranger_anxiety" | "group_size" | "conversation_load" | "travel_effort" | "time_commitment" | "cost" | "low_social_energy" | "push_aversion" | "not_today")[]
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
context: ConversationContext
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

export interface LiveEvent {
schemaVersion: "1.0"
id: string
provider: string
sourceRecordId: string
title: string
description: string
startsAt: string
endsAt: string
timezone: "Asia/Tokyo"
venueName: (string | null)
address: (string | null)
latitude: (number | null)
longitude: (number | null)
communityId: (string | null)
seriesId: (string | null)
status: ("scheduled" | "canceled" | "sold_out" | "registration_closed" | "ended" | "unknown")
registrationStatus: ("open" | "waitlist" | "sold_out" | "closed" | "not_required" | "unknown")
registrationDeadline: (string | null)
capacity: (number | null)
participants: (number | null)
audience?: (string | null)
priceYen: (number | null)
categories: string[]
sourceUrl: string
sourceDataset: string
license: string
sourceClassification: ("raw_open_data" | "live_provider" | "ai_derived" | "organizer_verified" | "private_user_data" | "synthetic_demo")
sourceLinks?: {
provider: string
sourceRecordId: string
sourceUrl: string
fetchedAt: string
classification: ("raw_open_data" | "live_provider" | "ai_derived" | "organizer_verified" | "private_user_data" | "synthetic_demo")
}[]
duplicateEventIds?: string[]
sourceUpdatedAt: string
fetchedAt: string
revalidatedAt: string
checksum: string
fieldProvenance: {
[k: string]: FieldProvenance
}
}

export interface EventSeries {
schemaVersion: "1.0"
id: string
provider: string
communityId: (string | null)
title: string
recurrenceText: string
futureOccurrenceIds: string[]
sourceUrl: string
sourceClassification: ("raw_open_data" | "live_provider" | "ai_derived" | "organizer_verified" | "private_user_data" | "synthetic_demo")
sourceUpdatedAt: string
fetchedAt: string
revalidatedAt: string
/**
 * @minItems 1
 */
evidence: [Evidence, ...(Evidence)[]]
}

export interface Community {
schemaVersion: "1.0"
id: string
provider: string
name: string
description: string
organizerName: (string | null)
eventSeriesIds: string[]
futureEventIds: string[]
communityUrl: string
sourceClassification: ("raw_open_data" | "live_provider" | "ai_derived" | "organizer_verified" | "private_user_data" | "synthetic_demo")
sourceUpdatedAt: string
fetchedAt: string
revalidatedAt: string
/**
 * @minItems 1
 */
evidence: [Evidence, ...(Evidence)[]]
}

export interface SourceRegistry {
schemaVersion: "1.0"
generatedAt: string
sources: Source[]
}

export interface ConnectionEvidence {
schemaVersion: "1.0"
eventId: string
connectionLevel: number
soloFriendly: ("yes" | "no" | "unknown")
beginnerFriendly: ("yes" | "no" | "unknown")
recurring: ("yes" | "no" | "unknown")
structuredConversation: ("yes" | "no" | "unknown")
sharedMeal: ("yes" | "no" | "unknown")
groupWork: ("yes" | "no" | "unknown")
roleAvailable: ("yes" | "no" | "unknown")
futureOccurrenceCount: number
solicitationRisk: ("low" | "medium" | "high" | "unknown")
/**
 * @minItems 1
 */
evidence: [Evidence, ...(Evidence)[]]
model: {
method: ("rules" | "ai" | "organizer_verified")
version: string
confidence: number
}
evaluatedAt: string
}

export interface Opportunity {
schemaVersion: "1.0"
id: string
sourceRecordId?: string
eventId?: string
communityId?: (string | null)
seriesId?: (string | null)
title: string
description?: string
startsAt: string
endsAt: string
address: string
latitude?: number
longitude?: number
priceYen: (number | null)
socialIntensity: number
conversationRequired: ("none" | "low" | "medium" | "high")
soloFriendly: boolean
recurring?: boolean
futureOccurrences?: {
eventId: string
startsAt: string
endsAt: string
sourceUrl: string
}[]
capacity?: (number | null)
participants?: (number | null)
status?: ("scheduled" | "canceled" | "sold_out" | "registration_closed" | "ended" | "unknown")
registrationStatus?: ("open" | "waitlist" | "sold_out" | "closed" | "not_required" | "unknown")
registrationDeadline?: (string | null)
flexibleVisit?: boolean
visitDurationMinutes?: number
roleAvailable?: (boolean | null)
roleDescription?: (string | null)
categories?: string[]
provider: string
sourceType: ("open_data" | "live_provider" | "organizer_verified" | "ai_derived" | "private_user_data")
sourceClassification?: ("raw_open_data" | "live_provider" | "ai_derived" | "organizer_verified" | "private_user_data" | "synthetic_demo")
sourceUrl: string
datasetUrl?: string
sourceDataset: string
license: string
capturedAt: string
sourceUpdatedAt?: string
fetchedAt?: string
revalidatedAt?: string
checksum: string
sourceTrust?: number
confidence?: number
dataMode: ("demo" | "live")
verificationStatus: ("synthetic_demo" | "source_snapshot" | "source_verified" | "organizer_verified" | "unverified")
fieldProvenance: {
[k: string]: FieldProvenance
}
connectionEvidence?: ConnectionEvidence
travelEstimate: {
[k: string]: any
}
}

export interface DecisionResult {
schemaVersion: "1.0"
episodeId: string
policyVersion: string
decision: ("do_not_push" | "check_in_only" | "suggest_solo_place" | "suggest_light_social" | "suggest_small_role")
shouldPush: boolean
reasonCodes: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "CONNECTION_LEVEL" | "REGISTRATION_UNAVAILABLE" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
score: (number | null)
selectedOpportunity: (Opportunity | null)
/**
 * @maxItems 8
 */
rankedOpportunities?: []|[RankedOpportunity]|[RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]
excludedCandidates: {
opportunityId: string
reasonCodes: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "CONNECTION_LEVEL" | "REGISTRATION_UNAVAILABLE" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
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
reasonCodes: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "CONNECTION_LEVEL" | "REGISTRATION_UNAVAILABLE" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
score: (number | null)
profileSnapshot: (DistanceProfile | null)
freeWindowSnapshot: (FreeWindow | null)
candidateIdsBeforeFilter: string[]
candidateIdsAfterFilter: string[]
excludedCandidates: {
opportunityId: string
reasonCodes: ("NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "CONNECTION_LEVEL" | "REGISTRATION_UNAVAILABLE" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET")[]
}[]
selectedOpportunity: (Opportunity | null)
/**
 * @maxItems 8
 */
rankedOpportunities?: []|[RankedOpportunity]|[RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]|[RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity, RankedOpportunity]
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

export type ChatRequest = ({
action: "start"
remember?: boolean
} | {
action?: "message"
message: string
remember?: boolean
} | {
action: "select"
opportunityId: string
remember?: boolean
} | {
action: "check_in"
message: string
remember?: boolean
})

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

export interface CalendarCallbackRequest {
state: string
code: string
}

export interface EventRouteRequest {
eventId: string
origin: {
latitude: number
longitude: number
}
}

export interface EventRouteResult {
eventId: string
mode: ("walk" | "transit")
minutes: number
source: "maps_verified"
computedAt: string
distanceMeters: number
confidence: number
resolvedAddress: string
latitude: number
longitude: number
}

export type SchemaVersion = "1.0";
export type DataMode = "demo" | "live";
export type MetricClassification = "measured" | "reference_estimate" | "demo" | "unverified";
export type SourceClassification = "raw_open_data" | "live_provider" | "ai_derived" | "organizer_verified" | "private_user_data" | "synthetic_demo";
export type EventStatus = "scheduled" | "canceled" | "sold_out" | "registration_closed" | "ended" | "unknown";
export type RegistrationStatus = "open" | "waitlist" | "sold_out" | "closed" | "not_required" | "unknown";
export type SocialIntensity = 0 | 1 | 2 | 3 | 4 | 5;
export type PushTone = "gentle" | "casual" | "direct" | "quiet";
export type ReasonCode = "NO_PUSH_CONSENT" | "QUIET_HOURS" | "COOLDOWN_ACTIVE" | "WEEKLY_LIMIT_REACHED" | "EXPLICIT_PAUSE" | "EXPLICIT_NO_ACTION" | "HUMAN_SUPPORT_REQUIRED" | "NO_FREE_WINDOW" | "NO_VERIFIED_OPPORTUNITY" | "OUTSIDE_FREE_WINDOW" | "TRAVEL_LIMIT" | "OVER_BUDGET" | "SOCIAL_INTENSITY_LIMIT" | "CONNECTION_LEVEL" | "REGISTRATION_UNAVAILABLE" | "INVALID_SOURCE" | "SCORE_BELOW_THRESHOLD" | "FREE_WINDOW_AVAILABLE" | "LOW_SOCIAL_BATTERY" | "LOW_CONVERSATION_REQUIREMENT" | "WITHIN_TRAVEL_LIMIT" | "UNDER_BUDGET";
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
