from __future__ import annotations

import unittest

from osekkai_safety import assess_safety


class SafetyTests(unittest.TestCase):
    def test_explicit_urgent_distress_stops_event_path_without_diagnosis(self):
        result = assess_safety("死にたい")
        self.assertTrue(result["requiresHumanSupport"])
        self.assertEqual(result["level"], "urgent")
        self.assertFalse(result["supportResourcesVerified"])
        self.assertNotIn("診断しました", result["message"])

    def test_tiredness_alone_is_not_a_diagnosis(self):
        result = assess_safety("今週は疲れた")
        self.assertFalse(result["requiresHumanSupport"])
        self.assertEqual(result["level"], "normal")


if __name__ == "__main__":
    unittest.main()
