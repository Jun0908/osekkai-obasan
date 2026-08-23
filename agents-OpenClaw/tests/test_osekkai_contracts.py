from __future__ import annotations

import copy
import json
import unittest

from helpers import AGENT_ROOT, NOW, USER_ID
from osekkai_contracts import (
    ContractError,
    validate_command_payload,
    validate_decision,
    validate_episode,
    validate_envelope,
    validate_freebusy,
    validate_opportunity,
    validate_profile,
    validate_reason_codes,
)


class ContractTests(unittest.TestCase):
    def fixture(self, name):
        with (AGENT_ROOT / "fixtures" / "osekkai" / name).open(encoding="utf-8") as handle:
            return json.load(handle)

    def test_profile_fixture_is_valid(self):
        self.assertEqual(validate_profile(self.fixture("profile.json"))["schemaVersion"], "1.0")

    def test_freebusy_fixture_is_privacy_minimal(self):
        validated = validate_freebusy(self.fixture("freebusy.json"))
        self.assertEqual(validated["freeWindows"][0]["durationMinutes"], 240)

    def test_calendar_title_is_rejected(self):
        value = self.fixture("freebusy.json")
        value["freeWindows"][0]["title"] = "private"
        with self.assertRaises(ContractError):
            validate_freebusy(value)

    def test_normalized_opportunity_is_valid(self):
        value = self.fixture("opportunities.normalized.json")["opportunities"][0]
        self.assertEqual(validate_opportunity(value)["verificationStatus"], "source_snapshot")

    def test_same_live_fixture_validates_new_models_and_ranked_candidates(self):
        fixture = self.fixture("live-contracts.json")
        from osekkai_contracts import validate_schema

        validate_schema(fixture["sourceRegistry"], "source-registry.schema.json")
        for key, schema in (
            ("events", "event.schema.json"),
            ("series", "event-series.schema.json"),
            ("communities", "community.schema.json"),
            ("connectionEvidence", "connection-evidence.schema.json"),
            ("opportunities", "opportunity.schema.json"),
        ):
            for value in fixture[key]:
                validate_schema(value, schema)
        decision = validate_decision(fixture["decision"])
        self.assertEqual([item["rank"] for item in decision["rankedOpportunities"]], [1, 2])

    def test_live_candidate_requires_freshness_source_and_connection_evidence(self):
        fixture = self.fixture("live-contracts.json")
        for missing in ("sourceUpdatedAt", "revalidatedAt", "connectionEvidence", "status"):
            invalid = copy.deepcopy(fixture["opportunities"][0])
            del invalid[missing]
            with self.assertRaises(ContractError, msg=missing):
                validate_opportunity(invalid)

    def test_ranked_candidates_reject_gaps_and_duplicate_ids(self):
        fixture = self.fixture("live-contracts.json")
        invalid = copy.deepcopy(fixture["decision"])
        invalid["rankedOpportunities"][1]["rank"] = 3
        with self.assertRaises(ContractError):
            validate_decision(invalid)
        invalid = copy.deepcopy(fixture["decision"])
        invalid["rankedOpportunities"][1]["opportunityId"] = invalid["rankedOpportunities"][0]["opportunityId"]
        with self.assertRaises(ContractError):
            validate_decision(invalid)

    def test_unknown_reason_code_is_rejected(self):
        with self.assertRaises(ContractError):
            validate_reason_codes(["NOT_A_REASON"])

    def test_envelope_rejects_unknown_command_and_traversal_id(self):
        base = {
            "schemaVersion": "1.0",
            "requestId": "test",
            "command": "profile-get",
            "userId": USER_ID,
            "idempotencyKey": None,
            "payload": {},
        }
        self.assertEqual(validate_envelope(base)["userId"], USER_ID)
        bad = copy.deepcopy(base)
        bad["userId"] = "../../profiles/victim"
        with self.assertRaises(ContractError):
            validate_envelope(bad)
        bad = copy.deepcopy(base)
        bad["command"] = "arbitrary-module"
        with self.assertRaises(ContractError):
            validate_envelope(bad)

    def test_mutation_requires_idempotency_key(self):
        with self.assertRaises(ContractError):
            validate_envelope(
                {
                    "schemaVersion": "1.0",
                    "requestId": "test",
                    "command": "chat",
                    "userId": USER_ID,
                    "idempotencyKey": None,
                    "payload": {"message": "hello"},
                }
            )

    def test_canonical_mutation_payloads_reject_unknown_and_ambiguous_fields(self):
        self.assertEqual(
            validate_command_payload("chat", {"message": "hello", "remember": False})["message"],
            "hello",
        )
        with self.assertRaises(ContractError):
            validate_command_payload("chat", {"message": "hello", "unknown": True})
        with self.assertRaises(ContractError):
            validate_command_payload(
                "feedback",
                {
                    "episodeId": "33333333-3333-4333-8333-333333333333",
                    "actionResponse": "accepted",
                    "distanceFeedback": "just_right",
                },
            )

    def test_new_episode_requires_positive_sequence_but_legacy_can_be_read(self):
        episode = {
            "schemaVersion": "1.0",
            "id": "33333333-3333-4333-8333-333333333333",
            "userId": USER_ID,
            "sequence": 1,
            "policyVersion": "osekkai-p0-v1",
            "decision": "do_not_push",
            "reasonCodes": ["NO_PUSH_CONSENT"],
            "shouldPush": False,
            "score": None,
            "profileSnapshot": None,
            "freeWindowSnapshot": None,
            "candidateIdsBeforeFilter": [],
            "candidateIdsAfterFilter": [],
            "excludedCandidates": [],
            "selectedOpportunity": None,
            "notification": None,
            "pushedAt": None,
            "noPushAt": NOW.isoformat(),
            "actionResponse": None,
            "actionResponseAt": None,
            "distanceFeedback": None,
            "distanceFeedbackAt": None,
            "attendedAt": None,
            "revisitedAt": None,
            "selfInitiatedAt": None,
            "dataMode": "demo",
            "metricClassification": "demo",
            "minimalRecord": True,
            "createdAt": NOW.isoformat(),
            "updatedAt": NOW.isoformat(),
        }
        self.assertEqual(validate_episode(episode)["sequence"], 1)
        invalid = copy.deepcopy(episode)
        invalid["sequence"] = 0
        with self.assertRaises(ContractError):
            validate_episode(invalid)
        legacy = copy.deepcopy(episode)
        del legacy["sequence"]
        with self.assertRaises(ContractError):
            validate_episode(legacy)
        self.assertNotIn("sequence", validate_episode(legacy, allow_legacy_sequence=True))


if __name__ == "__main__":
    unittest.main()
