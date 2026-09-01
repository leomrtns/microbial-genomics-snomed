from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from snomed_infectious.cli import _load_approved_scope, build_parser


class CliTest(unittest.TestCase):
  def test_scope_file_include_column_is_respected(self) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
      path = Path(temporary_directory) / "scope.tsv"
      path.write_text("include\tconcept_id\n1\t100\n0\t200\nyes\t300\n", encoding="utf-8")
      self.assertEqual(_load_approved_scope(path), {"100", "300"})

  def test_builtin_profiles_are_valid_json(self) -> None:
    config_directory = Path(__file__).parents[1] / "configs"
    for profile in ("core", "research", "expansive"):
      config = json.loads((config_directory / f"{profile}.json").read_text(encoding="utf-8"))
      self.assertEqual(config["profile"]["name"], profile)
      self.assertIn("infectious disease", config["snomed"]["hierarchy_roots"])

  def test_research_is_default_profile(self) -> None:
    args = build_parser().parse_args([
      "discover-scope", "--snomed-root", "/tmp/input", "--output-dir", "/tmp/output"
    ])
    self.assertEqual(args.profile, "research")


if __name__ == "__main__":
  unittest.main()
