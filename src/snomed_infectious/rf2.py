from __future__ import annotations

import csv
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator


IS_A_TYPE_ID = "116680003"
FSN_TYPE_ID = "900000000000003001"
SYNONYM_TYPE_ID = "900000000000013009"
DEFINITION_TYPE_ID = "900000000000550004"
PREFERRED_ACCEPTABILITY_ID = "900000000000548007"

DESCRIPTION_TYPE_NAMES = {
  FSN_TYPE_ID: "fully_specified_name",
  SYNONYM_TYPE_ID: "synonym",
  DEFINITION_TYPE_ID: "definition",
}


@dataclass(frozen=True)
class SnomedExtraction:
  concept_rows: list[dict[str, object]]
  disease_term_rows: list[dict[str, object]]
  agent_term_rows: list[dict[str, object]]
  agent_relationship_rows: list[dict[str, object]]
  files_read: list[str]


def extract_snomed(
  release_root: Path,
  disease_root_ids: set[str],
  causative_agent_attribute_id: str,
  gb_language_refset_id: str,
) -> SnomedExtraction:
  files = discover_snapshot_files(release_root)
  if not files["concept"] or not files["description"] or not files["relationship"]:
    raise ValueError(f"Could not find RF2 Snapshot terminology files beneath {release_root}")

  active_concepts = {
    row["id"]
    for path in files["concept"]
    for row in iter_rf2(path)
    if row.get("active") == "1"
  }
  missing_roots = disease_root_ids - active_concepts
  if missing_roots:
    raise ValueError(f"Disease root concept(s) not active or absent: {', '.join(sorted(missing_roots))}")

  children_by_parent: dict[str, set[str]] = defaultdict(set)
  for path in files["relationship"]:
    for row in iter_rf2(path):
      if row.get("active") == "1" and row.get("typeId") == IS_A_TYPE_ID:
        children_by_parent[row["destinationId"]].add(row["sourceId"])

  disease_concepts = transitive_descendants(disease_root_ids, children_by_parent) & active_concepts
  agent_relationships: list[dict[str, str]] = []
  agent_ids: set[str] = set()
  for path in files["relationship"]:
    for row in iter_rf2(path):
      if (
        row.get("active") == "1"
        and row.get("sourceId") in disease_concepts
        and row.get("typeId") == causative_agent_attribute_id
      ):
        agent_ids.add(row["destinationId"])
        agent_relationships.append(row)

  descriptions = _descriptions_for_concepts(files["description"], disease_concepts | agent_ids)
  preferred_description_ids = _preferred_description_ids(
    files["language"], set(descriptions), gb_language_refset_id
  )
  names_by_concept = _best_names(descriptions.values(), preferred_description_ids)

  disease_terms = [
    _description_output(row, row["id"] in preferred_description_ids)
    for row in descriptions.values()
    if row["conceptId"] in disease_concepts
  ]
  agent_terms = [
    _description_output(row, row["id"] in preferred_description_ids)
    for row in descriptions.values()
    if row["conceptId"] in agent_ids
  ]
  disease_terms.sort(key=lambda row: (str(row["concept_id"]), str(row["term_type"]), str(row["term"])))
  agent_terms.sort(key=lambda row: (str(row["concept_id"]), str(row["term_type"]), str(row["term"])))

  concept_rows = []
  for concept_id in sorted(disease_concepts, key=int):
    concept_rows.append({
      "concept_id": concept_id,
      "preferred_term": names_by_concept.get(concept_id, {}).get("preferred", ""),
      "fully_specified_name": names_by_concept.get(concept_id, {}).get("fsn", ""),
      "is_scope_root": concept_id in disease_root_ids,
    })

  relationship_rows = []
  for row in agent_relationships:
    relationship_rows.append({
      "disease_concept_id": row["sourceId"],
      "disease_term": _display_name(names_by_concept, row["sourceId"]),
      "relationship_type_id": row["typeId"],
      "relationship_type_term": "Causative agent",
      "agent_concept_id": row["destinationId"],
      "agent_term": _display_name(names_by_concept, row["destinationId"]),
      "relationship_group": row.get("relationshipGroup", ""),
      "relationship_id": row.get("id", ""),
    })
  relationship_rows.sort(key=lambda row: (str(row["disease_concept_id"]), str(row["agent_concept_id"])))

  return SnomedExtraction(
    concept_rows=concept_rows,
    disease_term_rows=disease_terms,
    agent_term_rows=agent_terms,
    agent_relationship_rows=relationship_rows,
    files_read=[str(path) for group in files.values() for path in group],
  )


def discover_snapshot_files(release_root: Path) -> dict[str, list[Path]]:
  discovered: dict[str, list[Path]] = {key: [] for key in ("concept", "description", "relationship", "language")}
  for path in release_root.rglob("*.txt"):
    parts = path.parts
    name = path.name
    if "Snapshot" not in parts:
      continue
    if name.startswith("sct2_Concept_") or name.startswith("sct2_ConceptUK"):
      discovered["concept"].append(path)
    elif name.startswith("sct2_Description_") or name.startswith("sct2_DescriptionUK"):
      discovered["description"].append(path)
    elif (
      (name.startswith("sct2_Relationship_") or name.startswith("sct2_RelationshipUK"))
      and "ConcreteValues" not in name
    ):
      discovered["relationship"].append(path)
    elif name.startswith("der2_cRefset_Language"):
      discovered["language"].append(path)
  for paths in discovered.values():
    paths.sort()
  return discovered


def iter_rf2(path: Path) -> Iterator[dict[str, str]]:
  with path.open("r", encoding="utf-8-sig", newline="") as handle:
    # RF2 is delimiter-separated, not CSV-quoted. A literal double quote in a
    # description must therefore never make the parser consume following rows.
    yield from csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)


def transitive_descendants(root_ids: set[str], children_by_parent: dict[str, set[str]]) -> set[str]:
  seen = set(root_ids)
  queue = deque(root_ids)
  while queue:
    parent = queue.popleft()
    for child in children_by_parent.get(parent, ()):
      if child not in seen:
        seen.add(child)
        queue.append(child)
  return seen


def _descriptions_for_concepts(paths: Iterable[Path], concept_ids: set[str]) -> dict[str, dict[str, str]]:
  descriptions: dict[str, dict[str, str]] = {}
  for path in paths:
    for row in iter_rf2(path):
      if row.get("active") == "1" and row.get("conceptId") in concept_ids:
        descriptions[row["id"]] = row
  return descriptions


def _preferred_description_ids(paths: Iterable[Path], description_ids: set[str], gb_refset_id: str) -> set[str]:
  preferred: set[str] = set()
  for path in paths:
    for row in iter_rf2(path):
      if (
        row.get("active") == "1"
        and row.get("refsetId") == gb_refset_id
        and row.get("acceptabilityId") == PREFERRED_ACCEPTABILITY_ID
        and row.get("referencedComponentId") in description_ids
      ):
        preferred.add(row["referencedComponentId"])
  return preferred


def _best_names(
  descriptions: Iterable[dict[str, str]], preferred_ids: set[str]
) -> dict[str, dict[str, str]]:
  names: dict[str, dict[str, str]] = defaultdict(dict)
  for row in descriptions:
    concept_id = row["conceptId"]
    if row.get("typeId") == FSN_TYPE_ID:
      names[concept_id]["fsn"] = row.get("term", "")
    if row.get("id") in preferred_ids and row.get("typeId") == SYNONYM_TYPE_ID:
      names[concept_id]["preferred"] = row.get("term", "")
  for values in names.values():
    values.setdefault("preferred", values.get("fsn", ""))
  return names


def _description_output(row: dict[str, str], preferred_gb: bool) -> dict[str, object]:
  return {
    "concept_id": row["conceptId"],
    "description_id": row["id"],
    "term": row.get("term", ""),
    "term_type": DESCRIPTION_TYPE_NAMES.get(row.get("typeId", ""), row.get("typeId", "")),
    "preferred_gb": preferred_gb,
    "language_code": row.get("languageCode", ""),
    "effective_time": row.get("effectiveTime", ""),
    "module_id": row.get("moduleId", ""),
  }


def _display_name(names: dict[str, dict[str, str]], concept_id: str) -> str:
  values = names.get(concept_id, {})
  return values.get("preferred") or values.get("fsn") or ""
