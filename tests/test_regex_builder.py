import unittest

from lowlevel_computer_use_mcp import regex_builder


class GuidedBuilderTests(unittest.TestCase):
    def test_guided_components_cover_literals_classes_groups_alternation_quantifiers_and_anchors(
        self,
    ):
        builder = regex_builder.GuidedBuilder(anchor_start=True, anchor_end=True)
        pattern = (
            builder.literal("ID:")
            .character_class("0-9")
            .quantify_last("+")
            .group(r"[A-Z]{2}")
            .alternate("NONE")
            .pattern()
        )

        self.assertEqual(pattern, r"^(?:ID:(?:[0-9])+([A-Z]{2})|NONE)$")

    def test_quantifier_requires_a_component(self):
        with self.assertRaises(ValueError):
            regex_builder.GuidedBuilder().quantify_last("+")


class RegexEvaluationTests(unittest.TestCase):
    def test_valid_unicode_multiline_pattern_and_capture_groups(self):
        result = regex_builder.evaluate(r"^(?P<word>\w+)$", "香港\nToronto", "mu")

        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 2)
        self.assertEqual(result["matches"][0]["named_groups"], {"word": "香港"})
        self.assertEqual(result["engine"], "Python re")

    def test_invalid_pattern_returns_syntax_feedback(self):
        result = regex_builder.evaluate("(", "sample")

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "syntax")

    def test_no_match_is_successful(self):
        result = regex_builder.evaluate("z+", "abc")

        self.assertTrue(result["ok"])
        self.assertEqual(result["matches"], [])

    def test_zero_width_matches_are_bounded_and_advance(self):
        result = regex_builder.evaluate(r"(?=a)", "aaa")

        self.assertTrue(result["ok"])
        self.assertEqual(
            [match["span"] for match in result["matches"]], [[0, 0], [1, 1], [2, 2]]
        )

    def test_plain_text_mode_differs_from_regex_mode(self):
        regex_result = regex_builder.evaluate("a.b", "a.b axb")
        plain_result = regex_builder.evaluate("a.b", "a.b axb", plain_text=True)

        self.assertEqual(regex_result["count"], 2)
        self.assertEqual(plain_result["count"], 1)
        self.assertEqual(plain_result["pattern"], r"a\.b")

    def test_adversarial_backtracking_is_terminated(self):
        result = regex_builder.evaluate(
            r"(a+)+$", "a" * 50_000 + "!", timeout_seconds=0.5
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_type"], "timeout")

    def test_pattern_and_sample_limits(self):
        pattern_result = regex_builder.evaluate(
            "x" * (regex_builder.MAX_PATTERN_LENGTH + 1), ""
        )
        sample_result = regex_builder.evaluate(
            "x", "x" * (regex_builder.MAX_SAMPLE_LENGTH + 1)
        )

        self.assertEqual(pattern_result["error_type"], "limit")
        self.assertEqual(sample_result["error_type"], "limit")


if __name__ == "__main__":
    unittest.main()
