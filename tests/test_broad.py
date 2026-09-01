from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from snomed_infectious.broad import discover_related_snomed


class BroadDiscoveryTest(unittest.TestCase):
  def test_polyhierarchy_and_cross_hierarchy_relationships(self) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
      root = Path(temporary_directory)
      terminology = root / "Edition" / "Snapshot" / "Terminology"
      language = root / "Edition" / "Snapshot" / "Refset" / "Language"
      terminology.mkdir(parents=True)
      language.mkdir(parents=True)
      concept_ids = ["40733004", "64572001", "100", "200", "201", "300", "400", "246093002"]
      _write_tsv(
        terminology / "sct2_Concept_Snapshot_INT_20260101.txt",
        ["id", "effectiveTime", "active", "moduleId", "definitionStatusId"],
        [[concept_id, "20260101", "1", "m", "d"] for concept_id in concept_ids],
      )
      _write_tsv(
        terminology / "sct2_Relationship_Snapshot_INT_20260101.txt",
        [
          "id", "effectiveTime", "active", "moduleId", "sourceId", "destinationId", "relationshipGroup",
          "typeId", "characteristicTypeId", "modifierId"
        ],
        [
          ["r1", "20260101", "1", "m", "100", "40733004", "0", "116680003", "i", "m"],
          ["r2", "20260101", "1", "m", "100", "64572001", "0", "116680003", "i", "m"],
          ["r3", "20260101", "1", "m", "201", "200", "0", "116680003", "i", "m"],
          ["r4", "20260101", "1", "m", "100", "201", "1", "246075003", "i", "m"],
          ["r5", "20260101", "1", "m", "300", "201", "1", "246093002", "i", "m"],
        ],
      )
      description_header = [
        "id", "effectiveTime", "active", "moduleId", "conceptId", "languageCode", "typeId", "term",
        "caseSignificanceId"
      ]
      fsns = {
        "40733004": "Infectious disease (disorder)",
        "64572001": "Disease (disorder)",
        "100": "Infection of urinary tract (disorder)",
        "200": "Domain Bacteria (organism)",
        "201": "Example bacterium (organism)",
        "300": "Example bacterium DNA test (observable entity)",
        "400": "Vaccine product (medicinal product)",
        "246093002": "Component (attribute)",
      }
      descriptions = []
      language_rows = []
      for index, (concept_id, fsn) in enumerate(fsns.items(), start=1):
        descriptions.append([f"d{index}", "20260101", "1", "m", concept_id, "en", "900000000000003001", fsn, "c"])
        language_rows.append([
          f"l{index}", "20260101", "1", "m", "900000000000508004", f"d{index}", "900000000000548007"
        ])
      _write_tsv(
        terminology / "sct2_Description_Snapshot-en_INT_20260101.txt", description_header, descriptions
      )
      _write_tsv(
        language / "der2_cRefset_LanguageSnapshot-en_INT_20260101.txt",
        ["id", "effectiveTime", "active", "moduleId", "refsetId", "referencedComponentId", "acceptabilityId"],
        language_rows,
      )
      config = {
        "hierarchy_roots": {
          "infectious disease": ["40733004"],
          "bacterium": ["200"],
          "vaccine product": ["400"],
        },
        "disease_root_labels": ["infectious disease"],
        "microbe_root_labels": ["bacterium"],
        "lexical_rules": {},
        "ambiguous_lexical_rules": [],
        "ambiguous_rule_semantic_tags": [],
        "causative_agent_attribute_id": "246075003",
        "gb_language_refset_id": "900000000000508004",
      }

      result = discover_related_snomed(root, config)
      candidates = {row["concept_id"]: row for row in result.candidate_rows}

      self.assertIn("100", candidates)  # Reached through either of two parents.
      self.assertIn("201", candidates)  # Microbial hierarchy and causative-agent destination.
      self.assertIn("300", candidates)  # Observable outside disease hierarchy, linked to bacterium.
      self.assertIn("400", candidates)  # Separate vaccine hierarchy.
      self.assertEqual(candidates["300"]["linked_microbes"], ["Example bacterium (organism)"])
      self.assertIn("Example bacterium", " ".join(candidates["100"]["relationship_summary"]))


def _write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
  with path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE, quotechar=None)
    writer.writerow(header)
    writer.writerows(rows)


if __name__ == "__main__":
  unittest.main()
