from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from .dmd import DmdExtraction


WIDE_COLUMNS = (
  "vocabulary",
  "entity_category",
  "concept_id",
  "preferred_name",
  "term",
  "term_type",
  "is_preferred",
  "is_current",
  "confidence",
  "why_included",
  "semantic_tag",
  "linked_disease_ids",
  "linked_diseases",
  "linked_microbe_ids",
  "linked_microbes",
  "relationship_summary",
  "medicine_level",
  "therapeutic_moiety_ids",
  "therapeutic_moieties",
  "generic_product_ids",
  "generic_products",
  "brand_product_ids",
  "brand_products",
  "ingredient_ids",
  "ingredients",
  "bnf_codes",
  "atc_codes",
  "description_id",
  "effective_time",
  "module_id",
  "source_release",
)


SNOMED_ONLY_COLUMNS = (
  "concept_id",
  "entity_category",
  "semantic_tag",
  "preferred_name",
  "term",
  "term_type",
  "is_preferred",
  "is_current",
  "confidence",
  "why_included",
  "linked_disease_ids",
  "linked_diseases",
  "linked_microbe_ids",
  "linked_microbes",
  "relationship_summary",
  "description_id",
  "effective_time",
  "module_id",
  "source_release",
)


DMD_ONLY_COLUMNS = (
  "concept_id",
  "medicine_level",
  "preferred_name",
  "term",
  "term_type",
  "is_preferred",
  "is_current",
  "why_included",
  "therapeutic_moiety_ids",
  "therapeutic_moieties",
  "generic_product_ids",
  "generic_products",
  "brand_product_ids",
  "brand_products",
  "ingredient_ids",
  "ingredients",
  "bnf_codes",
  "atc_codes",
  "relationship_summary",
  "source_release",
)


SHARED_MATRIX_COLUMNS = (
  "concept_id",
  "identical_terms",
  "snomed_preferred_names",
  "dmd_preferred_names",
  "snomed_terms",
  "dmd_terms",
  "snomed_entity_categories",
  "snomed_semantic_tags",
  "snomed_confidences",
  "snomed_why_included",
  "snomed_linked_disease_ids",
  "snomed_linked_diseases",
  "snomed_linked_microbe_ids",
  "snomed_linked_microbes",
  "snomed_relationship_summary",
  "dmd_medicine_levels",
  "dmd_therapeutic_moiety_ids",
  "dmd_therapeutic_moieties",
  "dmd_generic_product_ids",
  "dmd_generic_products",
  "dmd_brand_product_ids",
  "dmd_brand_products",
  "dmd_ingredient_ids",
  "dmd_ingredients",
  "dmd_bnf_codes",
  "dmd_atc_codes",
  "dmd_why_included",
  "dmd_relationship_summary",
  "dmd_current_status_values",
  "snomed_source_releases",
  "dmd_source_releases",
)


COLUMN_DESCRIPTIONS = {
  "vocabulary": "Source terminology: SNOMED CT UK or dm+d.",
  "entity_category": "Plain-language grouping intended for non-clinical users.",
  "concept_id": "Stable source identifier, always stored as text.",
  "preferred_name": "Best available GB English or dm+d display name for the concept.",
  "term": "One searchable name or synonym. Concepts repeat across rows when they have multiple terms.",
  "term_type": "Fully specified name, synonym, definition, name, description, or previous name.",
  "is_preferred": "1 when this row is the preferred display term; otherwise 0.",
  "is_current": "1 for current content; 0 for a dm+d invalid or discontinued record.",
  "confidence": "High for semantic/classification selection; medium for a lexical-only SNOMED match.",
  "why_included": "Auditable, plain-language rule or rules responsible for inclusion.",
  "semantic_tag": "SNOMED semantic domain from the fully specified name; blank for dm+d.",
  "linked_disease_ids": "Directly linked infectious-disease identifiers, pipe-separated.",
  "linked_diseases": "Human-readable names corresponding to linked_disease_ids.",
  "linked_microbe_ids": "Directly linked microbial or causative-agent identifiers, pipe-separated.",
  "linked_microbes": "Human-readable names corresponding to linked_microbe_ids.",
  "relationship_summary": "Readable summaries of relevant terminology relationships.",
  "medicine_level": "Human-readable dm+d product level; blank for SNOMED rows.",
  "therapeutic_moiety_ids": "Related dm+d VTM identifiers.",
  "therapeutic_moieties": "Related dm+d VTM names.",
  "generic_product_ids": "Related dm+d VMP identifiers.",
  "generic_products": "Related dm+d VMP names.",
  "brand_product_ids": "Related dm+d AMP identifiers.",
  "brand_products": "Related dm+d AMP names.",
  "ingredient_ids": "Related dm+d ingredient identifiers.",
  "ingredients": "Related dm+d ingredient names.",
  "bnf_codes": "Inherited or direct BNF classifications used for medicine selection.",
  "atc_codes": "Inherited or direct ATC classifications used for medicine selection.",
  "description_id": "SNOMED description identifier; blank for dm+d.",
  "effective_time": "SNOMED description effective date; blank for dm+d.",
  "module_id": "SNOMED module identifier; blank for dm+d.",
  "source_release": "Input release or archive supplying this row.",
  "also_in_dmd": "1 when this concept identifier also occurs in the dm+d matrix.",
  "dmd_matching_names": "dm+d preferred names observed for the same concept identifier.",
  "dmd_medicine_levels": "dm+d entity levels observed for the same concept identifier.",
  "also_in_snomed": "1 when this concept identifier also occurs in the SNOMED matrix.",
  "snomed_matching_names": "SNOMED preferred names observed for the same concept identifier.",
  "snomed_entity_categories": "SNOMED entity categories observed for the same concept identifier.",
}


def partition_vocabulary_matrices(
  wide_rows: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
  """Create mutually exclusive SNOMED-only, dm+d-only, and shared matrices."""
  snomed_rows = [dict(row) for row in wide_rows if row.get("vocabulary") == "SNOMED CT UK"]
  dmd_rows = [dict(row) for row in wide_rows if row.get("vocabulary") == "dm+d"]
  snomed_by_id = _crosswalk_values(snomed_rows, "entity_category")
  dmd_by_id = _crosswalk_values(dmd_rows, "medicine_level")
  shared_ids = set(snomed_by_id) & set(dmd_by_id)
  snomed_only_rows = [row for row in snomed_rows if str(row["concept_id"]) not in shared_ids]
  dmd_only_rows = [row for row in dmd_rows if str(row["concept_id"]) not in shared_ids]
  snomed_shared = _rows_grouped_by_id(snomed_rows, shared_ids)
  dmd_shared = _rows_grouped_by_id(dmd_rows, shared_ids)
  shared_rows = [
    _shared_concept_row(concept_id, snomed_shared[concept_id], dmd_shared[concept_id])
    for concept_id in sorted(shared_ids, key=_identifier_sort_key)
  ]
  overlap = {
    "shared_concept_ids": len(shared_ids),
    "shared_concept_ids_with_an_identical_term": sum(bool(row["identical_terms"]) for row in shared_rows),
    "shared_ids": sorted(shared_ids, key=_identifier_sort_key),
    "interpretation": (
      "The three matrices are mutually exclusive by concept_id. Shared identifiers are removed from both exclusive "
      "matrices and denormalised into one self-contained shared row per identifier."
    ),
  }
  return snomed_only_rows, dmd_only_rows, shared_rows, overlap


def matrix_column_descriptions(columns: tuple[str, ...]) -> dict[str, str]:
  descriptions = {}
  for column in columns:
    if column in COLUMN_DESCRIPTIONS:
      descriptions[column] = COLUMN_DESCRIPTIONS[column]
    elif column == "identical_terms":
      descriptions[column] = "Terms occurring identically in both vocabularies for this shared identifier."
    elif column.startswith("snomed_"):
      descriptions[column] = "SNOMED values for " + column.removeprefix("snomed_").replace("_", " ") + "."
    elif column.startswith("dmd_"):
      descriptions[column] = "dm+d values for " + column.removeprefix("dmd_").replace("_", " ") + "."
    else:
      descriptions[column] = column.replace("_", " ").capitalize() + "."
  return descriptions


def make_dmd_wide_rows(extraction: DmdExtraction, archive_path: Path) -> list[dict[str, object]]:
  terms_by_concept: dict[tuple[str, str], list[dict[str, object]]] = defaultdict(list)
  names: dict[tuple[str, str], str] = {}
  for row in extraction.term_rows:
    key = (str(row["entity_type"]), str(row["concept_id"]))
    terms_by_concept[key].append(row)
    if row["term_type"] == "name" or key not in names:
      names[key] = str(row["term"])

  targets: dict[tuple[str, str, str], set[tuple[str, str]]] = defaultdict(set)
  reverse: dict[tuple[str, str, str], set[tuple[str, str]]] = defaultdict(set)
  for row in extraction.relationship_rows:
    source = (str(row["source_type"]), str(row["source_id"]))
    target = (str(row["target_type"]), str(row["target_id"]))
    relationship = str(row["relationship"])
    targets[(source[0], source[1], relationship)].add(target)
    reverse[(target[0], target[1], relationship)].add(source)

  classification_by_key: dict[tuple[str, str], tuple[set[str], set[str]]] = {}
  for key, rows in terms_by_concept.items():
    bnf_codes = {str(code) for row in rows for code in row.get("bnf_codes", ())}
    atc_codes = {str(code) for row in rows for code in row.get("atc_codes", ())}
    classification_by_key[key] = (bnf_codes, atc_codes)

  output: list[dict[str, object]] = []
  for key, rows in terms_by_concept.items():
    entity_type, concept_id = key
    vmp_keys = _related_vmps(key, targets, reverse)
    vtm_keys = {
      target
      for vmp_key in vmp_keys
      for target in targets.get((vmp_key[0], vmp_key[1], "has_vtm"), ())
    }
    ingredient_keys = {
      target
      for vtm_key in vtm_keys
      for target in targets.get((vtm_key[0], vtm_key[1], "has_ingredient"), ())
    }
    amp_keys = {
      source
      for vmp_key in vmp_keys
      for source in reverse.get((vmp_key[0], vmp_key[1], "has_vmp"), ())
      if source[0] == "AMP"
    }
    if entity_type == "AMP":
      amp_keys.add(key)
    if entity_type == "AMPP":
      amp_keys.update(targets.get((entity_type, concept_id, "has_amp"), ()))

    bnf_codes: set[str] = set()
    atc_codes: set[str] = set()
    for classification_key in vmp_keys | amp_keys | {key}:
      direct_bnf, direct_atc = classification_by_key.get(classification_key, (set(), set()))
      bnf_codes.update(direct_bnf)
      atc_codes.update(direct_atc)

    relationship_summary = _dmd_relationship_summary(key, targets, names)
    why_included = _medicine_reason(bnf_codes, atc_codes)
    common = {
      "vocabulary": "dm+d",
      "entity_category": "anti-infective medicine",
      "concept_id": concept_id,
      "preferred_name": names.get(key, concept_id),
      "confidence": "high",
      "why_included": [why_included],
      "semantic_tag": "",
      "linked_disease_ids": [],
      "linked_diseases": [],
      "linked_microbe_ids": [],
      "linked_microbes": [],
      "relationship_summary": relationship_summary,
      "medicine_level": _medicine_level(entity_type),
      "therapeutic_moiety_ids": _ids(vtm_keys),
      "therapeutic_moieties": _names(vtm_keys, names),
      "generic_product_ids": _ids(vmp_keys),
      "generic_products": _names(vmp_keys, names),
      "brand_product_ids": _ids(amp_keys),
      "brand_products": _names(amp_keys, names),
      "ingredient_ids": _ids(ingredient_keys),
      "ingredients": _names(ingredient_keys, names),
      "bnf_codes": sorted(bnf_codes),
      "atc_codes": sorted(atc_codes),
      "description_id": "",
      "effective_time": "",
      "module_id": "",
      "source_release": archive_path.name,
    }
    for row in rows:
      output.append({
        **common,
        "term": row["term"],
        "term_type": str(row["term_type"]).replace("_", " "),
        "is_preferred": row["term_type"] == "name",
        "is_current": row["is_current"],
      })
  output.sort(key=lambda row: (str(row["medicine_level"]), str(row["concept_id"]), str(row["term"])))
  return output


def add_snomed_source_release(rows: list[dict[str, object]], release_root: Path) -> None:
  for row in rows:
    row["source_release"] = release_root.name
    for column in WIDE_COLUMNS:
      row.setdefault(column, "")


def _related_vmps(
  key: tuple[str, str],
  targets: dict[tuple[str, str, str], set[tuple[str, str]]],
  reverse: dict[tuple[str, str, str], set[tuple[str, str]]],
) -> set[tuple[str, str]]:
  entity_type, concept_id = key
  if entity_type == "VMP":
    return {key}
  if entity_type in {"AMP", "VMPP"}:
    return set(targets.get((entity_type, concept_id, "has_vmp"), ()))
  if entity_type == "AMPP":
    vmps: set[tuple[str, str]] = set()
    for amp in targets.get((entity_type, concept_id, "has_amp"), ()):
      vmps.update(targets.get((amp[0], amp[1], "has_vmp"), ()))
    for vmpp in targets.get((entity_type, concept_id, "has_vmpp"), ()):
      vmps.update(targets.get((vmpp[0], vmpp[1], "has_vmp"), ()))
    return vmps
  if entity_type == "VTM":
    return set(reverse.get((entity_type, concept_id, "has_vtm"), ()))
  if entity_type == "INGREDIENT":
    vmps: set[tuple[str, str]] = set()
    for vtm in reverse.get((entity_type, concept_id, "has_ingredient"), ()):
      vmps.update(reverse.get((vtm[0], vtm[1], "has_vtm"), ()))
    return vmps
  return set()


def _dmd_relationship_summary(
  key: tuple[str, str],
  targets: dict[tuple[str, str, str], set[tuple[str, str]]],
  names: dict[tuple[str, str], str],
) -> list[str]:
  summaries = []
  for relationship, label in (
    ("has_vtm", "therapeutic moiety"),
    ("has_vmp", "generic product"),
    ("has_amp", "branded product"),
    ("has_vmpp", "generic pack"),
    ("has_ingredient", "ingredient"),
  ):
    for target in targets.get((key[0], key[1], relationship), ()):
      summaries.append(f"{label} -> {names.get(target, target[1])} [{target[1]}]")
  return sorted(summaries)


def _medicine_reason(bnf_codes: set[str], atc_codes: set[str]) -> str:
  classifications = []
  if bnf_codes:
    classifications.append(f"BNF anti-infective classification: {','.join(sorted(bnf_codes))}")
  if atc_codes:
    classifications.append(f"ATC anti-infective classification: {','.join(sorted(atc_codes))}")
  if classifications:
    return "; ".join(classifications)
  return "related through the dm+d hierarchy to a BNF/ATC-classified anti-infective product"


def _medicine_level(entity_type: str) -> str:
  return {
    "VTM": "therapeutic moiety",
    "VMP": "generic medicinal product",
    "AMP": "branded or manufacturer medicinal product",
    "VMPP": "generic medicinal product pack",
    "AMPP": "branded or manufacturer medicinal product pack",
    "INGREDIENT": "ingredient substance",
  }.get(entity_type, entity_type)


def _ids(keys: set[tuple[str, str]]) -> list[str]:
  return sorted((concept_id for _, concept_id in keys), key=_identifier_sort_key)


def _names(keys: set[tuple[str, str]], names: dict[tuple[str, str], str]) -> list[str]:
  return sorted(names.get(key, key[1]) for key in keys)


def _identifier_sort_key(identifier: str) -> tuple[int, object]:
  return (0, int(identifier)) if identifier.isdigit() else (1, identifier)


def _crosswalk_values(
  rows: list[dict[str, object]], category_column: str
) -> dict[str, dict[str, set[str]]]:
  values: dict[str, dict[str, set[str]]] = defaultdict(lambda: {"names": set(), "categories": set()})
  for row in rows:
    concept_id = str(row["concept_id"])
    values[concept_id]["names"].add(str(row["preferred_name"]))
    values[concept_id]["categories"].add(str(row[category_column]))
  return values


def _terms_by_id(rows: list[dict[str, object]]) -> dict[str, set[str]]:
  terms: dict[str, set[str]] = defaultdict(set)
  for row in rows:
    terms[str(row["concept_id"])].add(str(row["term"]).casefold())
  return terms


def _rows_grouped_by_id(
  rows: list[dict[str, object]], concept_ids: set[str]
) -> dict[str, list[dict[str, object]]]:
  grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
  for row in rows:
    concept_id = str(row["concept_id"])
    if concept_id in concept_ids:
      grouped[concept_id].append(row)
  return grouped


def _shared_concept_row(
  concept_id: str,
  snomed_rows: list[dict[str, object]],
  dmd_rows: list[dict[str, object]],
) -> dict[str, object]:
  snomed_terms = _collect_values(snomed_rows, "term")
  dmd_terms = _collect_values(dmd_rows, "term")
  dmd_by_casefold = {term.casefold(): term for term in dmd_terms}
  identical_terms = sorted(
    {dmd_by_casefold[term.casefold()] for term in snomed_terms if term.casefold() in dmd_by_casefold}
  )
  return {
    "concept_id": concept_id,
    "identical_terms": identical_terms,
    "snomed_preferred_names": _collect_values(snomed_rows, "preferred_name"),
    "dmd_preferred_names": _collect_values(dmd_rows, "preferred_name"),
    "snomed_terms": snomed_terms,
    "dmd_terms": dmd_terms,
    "snomed_entity_categories": _collect_values(snomed_rows, "entity_category"),
    "snomed_semantic_tags": _collect_values(snomed_rows, "semantic_tag"),
    "snomed_confidences": _collect_values(snomed_rows, "confidence"),
    "snomed_why_included": _collect_values(snomed_rows, "why_included"),
    "snomed_linked_disease_ids": _collect_values(snomed_rows, "linked_disease_ids"),
    "snomed_linked_diseases": _collect_values(snomed_rows, "linked_diseases"),
    "snomed_linked_microbe_ids": _collect_values(snomed_rows, "linked_microbe_ids"),
    "snomed_linked_microbes": _collect_values(snomed_rows, "linked_microbes"),
    "snomed_relationship_summary": _collect_values(snomed_rows, "relationship_summary"),
    "dmd_medicine_levels": _collect_values(dmd_rows, "medicine_level"),
    "dmd_therapeutic_moiety_ids": _collect_values(dmd_rows, "therapeutic_moiety_ids"),
    "dmd_therapeutic_moieties": _collect_values(dmd_rows, "therapeutic_moieties"),
    "dmd_generic_product_ids": _collect_values(dmd_rows, "generic_product_ids"),
    "dmd_generic_products": _collect_values(dmd_rows, "generic_products"),
    "dmd_brand_product_ids": _collect_values(dmd_rows, "brand_product_ids"),
    "dmd_brand_products": _collect_values(dmd_rows, "brand_products"),
    "dmd_ingredient_ids": _collect_values(dmd_rows, "ingredient_ids"),
    "dmd_ingredients": _collect_values(dmd_rows, "ingredients"),
    "dmd_bnf_codes": _collect_values(dmd_rows, "bnf_codes"),
    "dmd_atc_codes": _collect_values(dmd_rows, "atc_codes"),
    "dmd_why_included": _collect_values(dmd_rows, "why_included"),
    "dmd_relationship_summary": _collect_values(dmd_rows, "relationship_summary"),
    "dmd_current_status_values": _collect_values(dmd_rows, "is_current"),
    "snomed_source_releases": _collect_values(snomed_rows, "source_release"),
    "dmd_source_releases": _collect_values(dmd_rows, "source_release"),
  }


def _collect_values(rows: list[dict[str, object]], column: str) -> list[str]:
  values: set[str] = set()
  for row in rows:
    value = row.get(column)
    if isinstance(value, (list, tuple, set)):
      values.update(str(item) for item in value if str(item))
    elif value is not None and str(value):
      values.add(str(value))
  return sorted(values)
