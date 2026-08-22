import { createHash } from "node:crypto";
import { readFile, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import standaloneCode from "ajv/dist/standalone/index.js";
import { compile } from "json-schema-to-typescript";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = resolve(frontendRoot, "..");
const contractRoot = join(repositoryRoot, "contracts", "osekkai");
const manifestPath = join(frontendRoot, "lib", "osekkai", "contract-manifest.generated.ts");
const typesPath = join(frontendRoot, "lib", "osekkai", "types.generated.ts");
const validatorsPath = join(frontendRoot, "lib", "osekkai", "validators.generated.ts");

const contractFiles = [
  "common.schema.json",
  "distance-profile.schema.json",
  "conversation.schema.json",
  "chat-result.schema.json",
  "freebusy.schema.json",
  "opportunity.schema.json",
  "decision.schema.json",
  "intervention-episode.schema.json",
  "metrics.schema.json",
  "chat-request.schema.json",
  "profile-update-request.schema.json",
  "feedback-request.schema.json",
  "intervention-record-request.schema.json",
  "decide-request.schema.json",
  "demo-reset-request.schema.json",
  "profile-delete-request.schema.json",
];

const typeRoots = [
  ["distance-profile.schema.json", "DistanceProfile"],
  ["conversation.schema.json", "ConversationTurn"],
  ["chat-result.schema.json", "ChatResult"],
  ["freebusy.schema.json", "FreeBusyResult"],
  ["opportunity.schema.json", "Opportunity"],
  ["decision.schema.json", "DecisionResult"],
  ["intervention-episode.schema.json", "InterventionEpisode"],
  ["metrics.schema.json", "MetricsResult"],
  ["chat-request.schema.json", "ChatRequest"],
  ["profile-update-request.schema.json", "ProfileUpdateRequest"],
  ["feedback-request.schema.json", "FeedbackRequest"],
  ["intervention-record-request.schema.json", "InterventionRecordRequest"],
  ["decide-request.schema.json", "DecideRequest"],
  ["demo-reset-request.schema.json", "DemoResetRequest"],
  ["profile-delete-request.schema.json", "ProfileDeleteRequest"],
];

const validatorRoots = {
  rawValidateDistanceProfile: "distance-profile.schema.json",
  rawValidateConversationTurn: "conversation.schema.json",
  rawValidateChatResult: "chat-result.schema.json",
  rawValidateFreeBusyResult: "freebusy.schema.json",
  rawValidateOpportunity: "opportunity.schema.json",
  rawValidateDecisionResult: "decision.schema.json",
  rawValidateInterventionEpisode: "intervention-episode.schema.json",
  rawValidateMetricsResult: "metrics.schema.json",
  rawValidateChatRequest: "chat-request.schema.json",
  rawValidateProfileUpdateRequest: "profile-update-request.schema.json",
  rawValidateFeedbackRequest: "feedback-request.schema.json",
  rawValidateInterventionRecordRequest: "intervention-record-request.schema.json",
  rawValidateDecideRequest: "decide-request.schema.json",
  rawValidateDemoResetRequest: "demo-reset-request.schema.json",
  rawValidateProfileDeleteRequest: "profile-delete-request.schema.json",
};

const schemas = new Map();
const records = [];
for (const name of contractFiles) {
  const path = join(contractRoot, name);
  const source = await readFile(path, "utf8");
  const schema = JSON.parse(source);
  if (schema.$schema !== "https://json-schema.org/draft/2020-12/schema" || typeof schema.$id !== "string") {
    throw new Error(`${name} is not a JSON Schema 2020-12 contract`);
  }
  schemas.set(name, schema);
  records.push({
    file: relative(repositoryRoot, path).replaceAll("\\", "/"),
    id: schema.$id,
    sha256: createHash("sha256").update(source).digest("hex"),
  });
}

const combinedHash = createHash("sha256").update(JSON.stringify(records)).digest("hex");
const manifest = `/* Generated from /contracts/osekkai. Do not edit. */\n` +
  `export const OSEKKAI_CONTRACT_HASH = ${JSON.stringify(combinedHash)} as const;\n` +
  `export const OSEKKAI_CONTRACTS = ${JSON.stringify(records, null, 2)} as const;\n`;

const dependencySchema = {
  $schema: "https://json-schema.org/draft/2020-12/schema",
  $id: "https://osekkai.local/contracts/generated-type-dependencies.schema.json",
  title: "OsekkaiContractDependencies",
  type: "object",
  additionalProperties: false,
  required: ["inferredPreference", "fieldProvenance", "freeWindow"],
  properties: {
    inferredPreference: { $ref: "common.schema.json#/$defs/inferredPreference" },
    fieldProvenance: { $ref: "common.schema.json#/$defs/fieldProvenance" },
    freeWindow: { $ref: "freebusy.schema.json#/$defs/freeWindow" },
  },
};
const dependencyTypes = await compile(dependencySchema, "OsekkaiContractDependencies", {
  bannerComment: "",
  cwd: contractRoot,
  format: false,
  declareExternallyReferenced: true,
  style: { singleQuote: true, semi: true, tabWidth: 2 },
  unknownAny: false,
});
const generatedTypeBlocks = [dependencyTypes.trim()];
for (const [file, rootName] of typeRoots) {
  const schema = structuredClone(schemas.get(file));
  schema.title = rootName;
  // json-schema-to-typescript models an object-level conditional as
  // `{ [key: string]: any } & ...`.  The runtime validator still receives the
  // canonical `allOf`; omitting it only for the static shape keeps the closed
  // Episode object useful to TypeScript callers.
  if (file === "intervention-episode.schema.json") delete schema.allOf;
  const block = await compile(schema, rootName, {
    bannerComment: "",
    cwd: contractRoot,
    format: false,
    declareExternallyReferenced: false,
    style: { singleQuote: true, semi: true, tabWidth: 2 },
    unknownAny: false,
  });
  generatedTypeBlocks.push(block.trim());
}

const common = schemas.get("common.schema.json");
const episode = schemas.get("intervention-episode.schema.json");
const decision = schemas.get("decision.schema.json");
const metrics = schemas.get("metrics.schema.json");
const union = (values) => values.filter((value) => value !== null).map(JSON.stringify).join(" | ");
const compatibilityTypes = `
export type SchemaVersion = ${JSON.stringify(common.$defs.schemaVersion.const)};
export type DataMode = ${union(common.$defs.dataMode.enum)};
export type MetricClassification = ${union(common.$defs.classification.enum)};
export type SocialIntensity = 0 | 1 | 2 | 3 | 4 | 5;
export type PushTone = ${union(common.$defs.pushTone.enum)};
export type ReasonCode = ${union(common.$defs.reasonCode.enum)};
export type DecisionType = ${union(decision.properties.decision.enum)};
export type ActionResponse = ${union(episode.properties.actionResponse.enum)};
export type DistanceFeedback = ${union(episode.properties.distanceFeedback.enum)};
export type MeasuredMetricKey = ${union(metrics.properties.metrics.items.properties.key.enum)};
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
`;
const types = `/* Generated from /contracts/osekkai by scripts/generate-osekkai-contracts.mjs. Do not edit. */\n\n${generatedTypeBlocks.join("\n\n")}\n${compatibilityTypes}`;

const ajv = new Ajv2020({
  allErrors: true,
  strict: true,
  schemas: [...schemas.values()],
  code: { esm: true, source: true },
});
addFormats(ajv);
const validatorIds = Object.fromEntries(
  Object.entries(validatorRoots).map(([exportName, file]) => [exportName, schemas.get(file).$id]),
);
const standalone = standaloneCode(ajv, validatorIds).replace(/^"use strict";\s*/, "");

const validatorWrappers = `
export type ValidationResult<T> =
  | { valid: true; value: T }
  | { valid: false; errors: string[] };

type StandaloneValidator = ((value: unknown) => boolean) & {
  errors?: Array<{ instancePath?: string; message?: string }> | null;
};

function validateWith<T>(name: string, validator: StandaloneValidator, value: unknown): ValidationResult<T> {
  if (validator(value)) return { valid: true, value: value as T };
  const errors = (validator.errors || []).map(
    (error) => \`${"${name}"}${"${error.instancePath || '/'}"} ${"${error.message || 'is invalid'}"}\`,
  );
  return { valid: false, errors: errors.length ? errors : [\`${"${name}"} is invalid\`] };
}

export const validateDistanceProfile = (value: unknown) =>
  validateWith<import('./types.generated').DistanceProfile>('DistanceProfile', rawValidateDistanceProfile, value);
export const validateConversationTurn = (value: unknown) =>
  validateWith<import('./types.generated').ConversationTurn>('ConversationTurn', rawValidateConversationTurn, value);
export const validateChatResult = (value: unknown) =>
  validateWith<import('./types.generated').ChatResult>('ChatResult', rawValidateChatResult, value);
export const validateFreeBusyResult = (value: unknown) =>
  validateWith<import('./types.generated').FreeBusyResult>('FreeBusyResult', rawValidateFreeBusyResult, value);
export const validateOpportunity = (value: unknown) =>
  validateWith<import('./types.generated').Opportunity>('Opportunity', rawValidateOpportunity, value);
export const validateDecisionResult = (value: unknown) =>
  validateWith<import('./types.generated').DecisionResult>('DecisionResult', rawValidateDecisionResult, value);
export const validateInterventionEpisode = (value: unknown) =>
  validateWith<import('./types.generated').InterventionEpisode>('InterventionEpisode', rawValidateInterventionEpisode, value);
export const validateMetricsResult = (value: unknown) =>
  validateWith<import('./types.generated').MetricsResult>('MetricsResult', rawValidateMetricsResult, value);
export const validateChatRequest = (value: unknown) =>
  validateWith<import('./types.generated').ChatRequest>('ChatRequest', rawValidateChatRequest, value);
export const validateProfileUpdateRequest = (value: unknown) =>
  validateWith<import('./types.generated').ProfileUpdateRequest>('ProfileUpdateRequest', rawValidateProfileUpdateRequest, value);
export const validateFeedbackRequest = (value: unknown) =>
  validateWith<import('./types.generated').FeedbackRequest>('FeedbackRequest', rawValidateFeedbackRequest, value);
export const validateInterventionRecordRequest = (value: unknown) =>
  validateWith<import('./types.generated').InterventionRecordRequest>('InterventionRecordRequest', rawValidateInterventionRecordRequest, value);
export const validateDecideRequest = (value: unknown) =>
  validateWith<import('./types.generated').DecideRequest>('DecideRequest', rawValidateDecideRequest, value);
export const validateDemoResetRequest = (value: unknown) =>
  validateWith<import('./types.generated').DemoResetRequest>('DemoResetRequest', rawValidateDemoResetRequest, value);
export const validateProfileDeleteRequest = (value: unknown) =>
  validateWith<import('./types.generated').ProfileDeleteRequest>('ProfileDeleteRequest', rawValidateProfileDeleteRequest, value);

type JsonRecord = Record<string, unknown>;
const isRecord = (value: unknown): value is JsonRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value);
const isString = (value: unknown): value is string => typeof value === 'string';
const isDateTime = (value: unknown): value is string =>
  isString(value) && Number.isFinite(Date.parse(value)) && /(?:Z|[+-]\\d{2}:\\d{2})$/.test(value);
const isDataMode = (value: unknown) => value === 'demo' || value === 'live';
const isInteger = (value: unknown) => Number.isInteger(value) && Number(value) >= 0;
const resultValue = <T>(result: ValidationResult<T>) => result.valid;
const hasExactKeys = (value: JsonRecord, keys: string[]) =>
  Object.keys(value).length === keys.length && keys.every((key) => Object.prototype.hasOwnProperty.call(value, key));

export function validateSessionResult(value: unknown): ValidationResult<import('./types').SessionResult> {
  const valid = isRecord(value) && hasExactKeys(value, ['csrfToken', 'expiresAt', 'dataMode']) &&
    isString(value.csrfToken) && value.csrfToken.length > 0 &&
    isDateTime(value.expiresAt) && isDataMode(value.dataMode);
  return valid
    ? { valid: true, value: value as unknown as import('./types').SessionResult }
    : { valid: false, errors: ['SessionResult is invalid'] };
}

export function validateOpportunitiesResult(value: unknown): ValidationResult<import('./types').OpportunitiesResult> {
  const valid = isRecord(value) && hasExactKeys(value, ['schemaVersion', 'dataMode', 'notice', 'opportunities']) &&
    value.schemaVersion === '1.0' && isDataMode(value.dataMode) &&
    isString(value.notice) && Array.isArray(value.opportunities) &&
    value.opportunities.every((item) => resultValue(validateOpportunity(item)));
  return valid
    ? { valid: true, value: value as unknown as import('./types').OpportunitiesResult }
    : { valid: false, errors: ['OpportunitiesResult is invalid'] };
}

export function validateInterventionsResult(value: unknown): ValidationResult<import('./types').InterventionsResult> {
  const valid = isRecord(value) && hasExactKeys(value, ['schemaVersion', 'interventions']) &&
    value.schemaVersion === '1.0' && Array.isArray(value.interventions) &&
    value.interventions.every((item) => resultValue(validateInterventionEpisode(item)));
  return valid
    ? { valid: true, value: value as unknown as import('./types').InterventionsResult }
    : { valid: false, errors: ['InterventionsResult is invalid'] };
}

export function validateDecideResponse(value: unknown): ValidationResult<import('./types').DecideResponse> {
  const valid = isRecord(value) && hasExactKeys(value, ['decision', 'episode']) &&
    resultValue(validateDecisionResult(value.decision)) &&
    resultValue(validateInterventionEpisode(value.episode)) && isRecord(value.decision) &&
    isRecord(value.episode) && value.decision.episodeId === value.episode.id;
  return valid
    ? { valid: true, value: value as unknown as import('./types').DecideResponse }
    : { valid: false, errors: ['DecideResponse is invalid'] };
}

export function validateFeedbackResponse(value: unknown): ValidationResult<import('./types').FeedbackResponse> {
  const valid = isRecord(value) && hasExactKeys(value, ['episode', 'profile', 'alternativeOpportunity', 'message']) &&
    resultValue(validateInterventionEpisode(value.episode)) &&
    resultValue(validateDistanceProfile(value.profile)) &&
    (value.alternativeOpportunity === null || resultValue(validateOpportunity(value.alternativeOpportunity))) &&
    (value.message === null || isString(value.message));
  return valid
    ? { valid: true, value: value as unknown as import('./types').FeedbackResponse }
    : { valid: false, errors: ['FeedbackResponse is invalid'] };
}

export function validateRecordOutcomeResponse(value: unknown): ValidationResult<import('./types').RecordOutcomeResponse> {
  const valid = isRecord(value) && hasExactKeys(value, ['episode', 'recordedOutcome']) &&
    resultValue(validateInterventionEpisode(value.episode)) &&
    ['attended', 'revisited', 'self_initiated'].includes(String(value.recordedOutcome));
  return valid
    ? { valid: true, value: value as unknown as import('./types').RecordOutcomeResponse }
    : { valid: false, errors: ['RecordOutcomeResponse is invalid'] };
}

export function validateProfileDeleteResponse(value: unknown): ValidationResult<import('./types').ProfileDeleteResponse> {
  const valid = isRecord(value) && hasExactKeys(value, ['schemaVersion', 'deleted', 'deletedCounts']) &&
    value.schemaVersion === '1.0' && value.deleted === true &&
    isRecord(value.deletedCounts) && Object.values(value.deletedCounts).every(isInteger);
  return valid
    ? { valid: true, value: value as unknown as import('./types').ProfileDeleteResponse }
    : { valid: false, errors: ['ProfileDeleteResponse is invalid'] };
}

export function validateDemoResetResponse(value: unknown): ValidationResult<import('./types').DemoResetResponse> {
  const valid = isRecord(value) && hasExactKeys(value, [
    'schemaVersion', 'dataMode', 'resetAt', 'deleted', 'profile', 'freebusy',
    'opportunities', 'interventions', 'metrics',
  ]) && value.schemaVersion === '1.0' && value.dataMode === 'demo' &&
    isDateTime(value.resetAt) && isRecord(value.deleted) && Object.values(value.deleted).every(isInteger) &&
    resultValue(validateDistanceProfile(value.profile)) && resultValue(validateFreeBusyResult(value.freebusy)) &&
    resultValue(validateOpportunitiesResult(value.opportunities)) &&
    resultValue(validateInterventionsResult(value.interventions)) && resultValue(validateMetricsResult(value.metrics));
  return valid
    ? { valid: true, value: value as unknown as import('./types').DemoResetResponse }
    : { valid: false, errors: ['DemoResetResponse is invalid'] };
}
`;
const validators = `/* Generated standalone validators. Root schemas are not read at runtime. Do not edit. */\n// @ts-nocheck\n${standalone}\n${validatorWrappers}`;

await Promise.all([
  writeFile(manifestPath, manifest, "utf8"),
  writeFile(typesPath, types, "utf8"),
  writeFile(validatorsPath, validators, "utf8"),
]);
console.log(`Generated types and standalone validators for ${records.length} contracts; manifest ${combinedHash.slice(0, 12)}`);
