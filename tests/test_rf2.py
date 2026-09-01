from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from snomed_infectious.rf2 import extract_snomed


class Rf2ExtractionTest(unittest.TestCase):
  def test_extracts_descendants_terms_and_direct_agents(self) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
      root = Path(temporary_directory)
      terminology = root / "Edition" / "Snapshot" / "Terminology"
      language = root / "Edition" / "Snapshot" / "Refset" / "Language"
      terminology.mkdir(parents=True)
      language.mkdir(parents=True)

      _write_tsv(
        terminology / "sct2_Concept_Snapshot_INT_20260101.txt",
        ["id", "effectiveTime", "active", "moduleId", "definitionStatusId"],
        [
          ["40733004", "20260101", "1", "m", "d"],
          ["100001", "20260101", "1", "m", "d"],
          ["100002", "20260101", "1", "m", "d"],
          ["200001", "20260101", "1", "m", "d"],
        ],
      )
      _write_tsv(
        terminology / "sct2_Relationship_Snapshot_INT_20260101.txt",
        [
          "id", "effectiveTime", "active", "moduleId", "sourceId", "destinationId", "relationshipGroup",
          "typeId", "characteristicTypeId", "modifierId"
        ],
        [
          ["r1", "20260101", "1", "m", "100001", "40733004", "0", "116680003", "i", "m"],
          ["r2", "20260101", "1", "m", "100002", "100001", "0", "116680003", "i", "m"],
          ["r3", "20260101", "1", "m", "100002", "200001", "1", "246075003", "i", "m"],
        ],
      )
      description_header = [
        "id", "effectiveTime", "active", "moduleId", "conceptId", "languageCode", "typeId", "term",
        "caseSignificanceId"
      ]
      _write_tsv(
        terminology / "sct2_Description_Snapshot-en_INT_20260101.txt",
        description_header,
        [
          ["d1", "20260101", "1", "m", "40733004", "en", "900000000000003001", "Infectious disease (disorder)", "c"],
          ["d2", "20260101", "1", "m", "40733004", "en", "900000000000013009", "Infectious disease", "c"],
          ["d3", "20260101", "1", "m", "100001", "en", "900000000000013009", "Test infection", "c"],
          ["d4", "20260101", "1", "m", "100002", "en", "900000000000013009", '"Quoted infection', "c"],
          ["d5", "20260101", "1", "m", "200001", "en", "900000000000013009", "Test bacterium", "c"],
        ],
      )
      _write_tsv(
        language / "der2_cRefset_LanguageSnapshot-en_INT_20260101.txt",
        ["id", "effectiveTime", "active", "moduleId", "refsetId", "referencedComponentId", "acceptabilityId"],
        [["l1", "20260101", "1", "m", "900000000000508004", "d2", "900000000000548007"]],
      )

      result = extract_snomed(root, {"40733004"}, "246075003", "900000000000508004")

      self.assertEqual({row["concept_id"] for row in result.concept_rows}, {"40733004", "100001", "100002"})
      self.assertEqual({row["term"] for row in result.agent_term_rows}, {"Test bacterium"})
      self.assertIn('"Quoted infection', {row["term"] for row in result.disease_term_rows})
      self.assertEqual(result.agent_relationship_rows[0]["agent_concept_id"], "200001")
      preferred = {row["description_id"]: row["preferred_gb"] for row in result.disease_term_rows}
      self.assertTrue(preferred["d2"])


def _write_tsv(path: Path, header: list[str], rows: list[list[str]]) -> None:
  with path.open("w", encoding="utf-8", newline="") as handle:
    writer = csv.writer(handle, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_NONE, quotechar=None)
    writer.writerow(header)
    writer.writerows(rows)


if __name__ == "__main__":
  unittest.main()
