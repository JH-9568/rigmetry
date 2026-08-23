import unittest

from tag_utils import normalize_tag


class NormalizeTagTests(unittest.TestCase):
    def test_lowercases_and_trims(self) -> None:
        self.assertEqual(normalize_tag("  Release  "), "release")

    def test_collapses_multiple_spaces(self) -> None:
        self.assertEqual(normalize_tag("bug   fix"), "bug-fix")

    def test_collapses_mixed_whitespace(self) -> None:
        self.assertEqual(normalize_tag("docs\t update\nnow"), "docs-update-now")

    def test_preserves_existing_hyphens(self) -> None:
        self.assertEqual(normalize_tag("good-first issue"), "good-first-issue")


if __name__ == "__main__":
    unittest.main()
