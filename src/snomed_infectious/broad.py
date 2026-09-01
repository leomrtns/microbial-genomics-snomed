from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from .rf2 import (
  FSN_TYPE_ID,
  IS_A_TYPE_ID,
  _best_names,
  _descriptions_for_concepts,
  _preferred_description_ids,
  discover_snapshot_files,
  iter_rf2,
  transitive_descendants,
)


@dataclass(frozen=True)
class BroadSnomedExtraction:
  term_rows: list[dict[str, object]]
  candidate_rows: list[dict[str, object]]
  summary: dict[str, object]
  files_read: list[str]


def discover_related_snomed(
  release_root: Path,
  config: dict[str, object],
) -> BroadSnomedExtraction:
  """Discover cross-hierarchy microbial concepts and denormalise them into readable rows."""
  files = discover_snapshot_files(release_root)
  active_concepts = {
    row["id"]
    for path in files["concept"]
    for row in iter_rf2(path)
    if row.get("active") == "1"
  }

  children_by_parent: dict[str, set[str]] = defaultdict(set)
  for path in files["relationship"]:
    for row in iter_rf2(path):
      if row.get("active") == "1" and row.get("typeId") == IS_A_TYPE_ID:
        children_by_parent[row["destinationId"]].add(row["sourceId"])

  hierarchy_roots = config["hierarchy_roots"]
  disease_labels = set(config["disease_root_labels"])
  microbe_labels = set(config["microbe_root_labels"])
  reasons: dict[str, set[str]] = defaultdict(set)
  confidence: dict[str, str] = {}
  concepts_by_label: dict[str, set[str]] = {}
  for label, root_ids in hierarchy_roots.items():
    missing = set(root_ids) - active_concepts
    if missing:
      raise ValueError(f"Configured SNOMED root(s) not active or absent for {label}: {sorted(missing)}")
    descendants = transitive_descendants(set(root_ids), children_by_parent) & active_concepts
    concepts_by_label[label] = descendants
    for concept_id in descendants:
      reasons[concept_id].add(f"semantic descendant of {label} [{','.join(root_ids)}]")
      confidence[concept_id] = "high"

  disease_ids = set().union(*(concepts_by_label[label] for label in disease_labels))
  microbe_ids = set().union(*(concepts_by_label[label] for label in microbe_labels))

  direct_agent_ids: set[str] = set()
  causative_agent_attribute_id = str(config["causative_agent_attribute_id"])
  linked_diseases: dict[str, set[str]] = defaultdict(set)
  linked_microbes: dict[str, set[str]] = defaultdict(set)
  for path in files["relationship"]:
    for row in iter_rf2(path):
      if (
        row.get("active") == "1"
        and row.get("typeId") == causative_agent_attribute_id
        and row.get("sourceId") in disease_ids
      ):
        direct_agent_ids.add(row["destinationId"])
        linked_microbes[row["sourceId"]].add(row["destinationId"])
        linked_diseases[row["destinationId"]].add(row["sourceId"])

  direct_agent_ids &= active_concepts
  for concept_id in direct_agent_ids:
    reasons[concept_id].add("direct causative agent of an infectious disease")
    confidence[concept_id] = "high"
  semantic_target_ids = disease_ids | microbe_ids | direct_agent_ids

  relationship_edges: list[dict[str, str]] = []
  relationship_type_ids: set[str] = set()
  structured_sources: set[str] = set()
  for path in files["relationship"]:
    for row in iter_rf2(path):
      if row.get("active") != "1" or row.get("typeId") == IS_A_TYPE_ID:
        continue
      source_id = row["sourceId"]
      destination_id = row["destinationId"]
      if destination_id not in semantic_target_ids:
        continue
      structured_sources.add(source_id)
      relationship_type_ids.add(row["typeId"])
      relationship_edges.append(row)
      target_kind = "infectious disease" if destination_id in disease_ids else "microbe or infectious agent"
      reasons[source_id].add(f"defining SNOMED relationship to scoped {target_kind}")
      confidence[source_id] = "high"
      if destination_id in disease_ids:
        linked_diseases[source_id].add(destination_id)
      if destination_id in microbe_ids or destination_id in direct_agent_ids:
        linked_microbes[source_id].add(destination_id)
        if source_id in disease_ids:
          linked_diseases[destination_id].add(source_id)

  structured_family = transitive_descendants(structured_sources, children_by_parent) & active_concepts
  for concept_id in structured_family - structured_sources:
    reasons[concept_id].add("descendant of a concept with a defining relationship to a disease or microbe")
    confidence[concept_id] = "high"

  lexical_patterns = {
    label: re.compile(pattern, re.IGNORECASE)
    for label, pattern in config.get("lexical_rules", {}).items()
  }
  ambiguous_rules = set(config.get("ambiguous_lexical_rules", ()))
  allowed_ambiguous_tags = set(config.get("ambiguous_rule_semantic_tags", ()))
  for path in files["description"]:
    for row in iter_rf2(path):
      if row.get("active") != "1" or row.get("typeId") != FSN_TYPE_ID:
        continue
      term = row.get("term", "")
      semantic_tag = semantic_tag_from_fsn(term)
      for label, pattern in lexical_patterns.items():
        if not pattern.search(term):
          continue
        if label in ambiguous_rules and semantic_tag not in allowed_ambiguous_tags:
          continue
        concept_id = row["conceptId"]
        reasons[concept_id].add(f"FSN matches microbial rule: {label}")
        confidence.setdefault(concept_id, "medium")

  candidate_ids = set(reasons) & active_concepts
  descriptions = _descriptions_for_concepts(files["description"], candidate_ids)
  preferred_ids = _preferred_description_ids(
    files["language"], set(descriptions), str(config["gb_language_refset_id"])
  )
  names = _best_names(descriptions.values(), preferred_ids)
  attribute_names = _fsn_names(files["description"], relationship_type_ids)

  relationship_summaries: dict[str, set[str]] = defaultdict(set)
  for edge in relationship_edges:
    source_id = edge["sourceId"]
    destination_id = edge["destinationId"]
    target_name = _display_name(names, destination_id)
    attribute_name = attribute_names.get(edge["typeId"], edge["typeId"])
    relationship_summaries[source_id].add(
      f"{_without_semantic_tag(attribute_name)} -> {target_name} [{destination_id}]"
    )

  descriptions_by_concept: dict[str, list[dict[str, str]]] = defaultdict(list)
  for row in descriptions.values():
    descriptions_by_concept[row["conceptId"]].append(row)

  candidate_rows: list[dict[str, object]] = []
  term_rows: list[dict[str, object]] = []
  category_counts: Counter[str] = Counter()
  confidence_counts: Counter[str] = Counter()
  for concept_id in sorted(candidate_ids, key=int):
    fsn = names.get(concept_id, {}).get("fsn", "")
    preferred_name = _display_name(names, concept_id)
    semantic_tag = semantic_tag_from_fsn(fsn)
    category = plain_category(concept_id, semantic_tag, disease_ids, microbe_ids, reasons[concept_id])
    shared = {
      "concept_id": concept_id,
      "entity_category": category,
      "semantic_tag": semantic_tag,
      "preferred_name": preferred_name,
      "fully_specified_name": fsn,
      "confidence": confidence[concept_id],
      "why_included": sorted(reasons[concept_id]),
      "linked_disease_ids": sorted(linked_diseases.get(concept_id, ()), key=int),
      "linked_diseases": sorted(
        _display_name(names, linked_id) for linked_id in linked_diseases.get(concept_id, ())
      ),
      "linked_microbe_ids": sorted(linked_microbes.get(concept_id, ()), key=int),
      "linked_microbes": sorted(
        _display_name(names, linked_id) for linked_id in linked_microbes.get(concept_id, ())
      ),
      "relationship_summary": sorted(relationship_summaries.get(concept_id, ())),
    }
    candidate_rows.append({
      **shared,
      "include_by_default": True,
      "active_term_count": len(descriptions_by_concept.get(concept_id, ())),
    })
    category_counts[category] += 1
    confidence_counts[confidence[concept_id]] += 1
    for description in descriptions_by_concept.get(concept_id, ()):
      term_rows.append({
        **shared,
        "vocabulary": "SNOMED CT UK",
        "term": description.get("term", ""),
        "term_type": _term_type(description.get("typeId", "")),
        "is_preferred": description["id"] in preferred_ids,
        "is_current": True,
        "description_id": description["id"],
        "effective_time": description.get("effectiveTime", ""),
        "module_id": description.get("moduleId", ""),
      })

  term_rows.sort(key=lambda row: (str(row["entity_category"]), str(row["concept_id"]), str(row["term"])))
  return BroadSnomedExtraction(
    term_rows=term_rows,
    candidate_rows=candidate_rows,
    summary={
      "candidate_concepts": len(candidate_rows),
      "active_terms": len(term_rows),
      "concepts_by_category": dict(sorted(category_counts.items())),
      "concepts_by_confidence": dict(sorted(confidence_counts.items())),
      "infectious_disease_concepts": len(disease_ids),
      "microbe_concepts": len(microbe_ids),
      "direct_causative_agent_concepts": len(direct_agent_ids),
      "relationship_selected_concepts": len(structured_sources),
      "lexical_rules": list(lexical_patterns),
    },
    files_read=[str(path) for group in files.values() for path in group],
  )


def semantic_tag_from_fsn(fsn: str) -> str:
  match = re.search(r"\(([^()]*)\)\s*$", fsn)
  return match.group(1) if match else ""


def plain_category(
  concept_id: str,
  semantic_tag: str,
  disease_ids: set[str],
  microbe_ids: set[str],
  reasons: set[str],
) -> str:
  if concept_id in disease_ids:
    return "infectious disease or condition"
  if concept_id in microbe_ids:
    return "microbe or infectious agent"
  if semantic_tag == "organism":
    return "microbe or infectious agent"
  joined_reasons = " ".join(reasons).lower()
  if "vaccine product" in joined_reasons or "vaccine or immunisation" in joined_reasons:
    return "vaccine or immunisation"
  if semantic_tag == "specimen":
    return "specimen"
  if semantic_tag == "observable entity":
    return "laboratory test or observable"
  if semantic_tag == "procedure":
    return "procedure"
  if semantic_tag in {"medicinal product", "medicinal product form", "clinical drug", "product"}:
    return "medicine or product"
  if semantic_tag == "substance":
    return "substance or ingredient"
  if semantic_tag in {"disorder", "finding", "situation"}:
    return "related clinical finding"
  return "other related concept"


def _fsn_names(paths: list[Path], concept_ids: set[str]) -> dict[str, str]:
  names: dict[str, str] = {}
  for path in paths:
    for row in iter_rf2(path):
      if (
        row.get("active") == "1"
        and row.get("typeId") == FSN_TYPE_ID
        and row.get("conceptId") in concept_ids
      ):
        names[row["conceptId"]] = row.get("term", "")
  return names


def _display_name(names: dict[str, dict[str, str]], concept_id: str) -> str:
  values = names.get(concept_id, {})
  return values.get("preferred") or _without_semantic_tag(values.get("fsn", "")) or concept_id


def _without_semantic_tag(term: str) -> str:
  return re.sub(r"\s+\([^()]*\)\s*$", "", term)


def _term_type(type_id: str) -> str:
  return {
    "900000000000003001": "fully specified name",
    "900000000000013009": "synonym",
    "900000000000550004": "definition",
  }.get(type_id, type_id)
