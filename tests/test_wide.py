from __future__ import annotations

import unittest

from snomed_infectious.wide import partition_vocabulary_matrices


class VocabularySplitTest(unittest.TestCase):
  def test_splits_rows_and_denormalises_shared_identifier(self) -> None:
    rows = [
      {
        "vocabulary": "SNOMED CT UK",
        "concept_id": "123",
        "preferred_name": "Example antibiotic",
        "term": "Example antibiotic",
        "entity_category": "substance or ingredient",
      },
      {
        "vocabulary": "dm+d",
        "concept_id": "123",
        "preferred_name": "Example antibiotic",
        "term": "Example antibiotic",
        "medicine_level": "ingredient substance",
      },
      {
        "vocabulary": "dm+d",
        "concept_id": "456",
        "preferred_name": "Example tablets",
        "term": "Example tablets",
        "medicine_level": "generic medicinal product",
      },
    ]

    snomed_rows, dmd_rows, shared_rows, overlap = partition_vocabulary_matrices(rows)

    self.assertEqual(len(snomed_rows), 0)
    self.assertEqual(len(dmd_rows), 1)
    self.assertEqual(dmd_rows[0]["concept_id"], "456")
    self.assertEqual(len(shared_rows), 1)
    self.assertEqual(shared_rows[0]["concept_id"], "123")
    self.assertEqual(shared_rows[0]["dmd_medicine_levels"], ["ingredient substance"])
    self.assertEqual(shared_rows[0]["identical_terms"], ["Example antibiotic"])
    self.assertEqual(overlap["shared_concept_ids"], 1)
    self.assertEqual(overlap["shared_concept_ids_with_an_identical_term"], 1)


if __name__ == "__main__":
  unittest.main()
