from __future__ import annotations

import io
import tarfile
import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator


@dataclass(frozen=True)
class DmdExtraction:
  term_rows: list[dict[str, object]]
  relationship_rows: list[dict[str, object]]
  selected_vmp_ids: set[str]
  selected_amp_ids: set[str]
  files_read: list[str]


def extract_dmd(
  core_archive: Path,
  bonus_archive: Path,
  bnf_prefixes: tuple[str, ...],
  atc_prefixes: tuple[str, ...],
) -> DmdExtraction:
  vmp_classes, amp_classes, bnf_member = _read_classifications(bonus_archive)
  direct_vmp_reasons = {
    concept_id: _selection_reasons(values, bnf_prefixes, atc_prefixes)
    for concept_id, values in vmp_classes.items()
    if _selection_reasons(values, bnf_prefixes, atc_prefixes)
  }
  direct_amp_reasons = {
    concept_id: _selection_reasons(values, bnf_prefixes, ())
    for concept_id, values in amp_classes.items()
    if _selection_reasons(values, bnf_prefixes, ())
  }

  amp_records = {
    row["APID"]: row
    for row in _iter_archive_records(core_archive, "f_amp2_", "AMP")
    if row.get("APID") and row.get("VPID")
  }
  selected_vmp_ids = set(direct_vmp_reasons)
  selected_vmp_ids.update(
    amp_records[amp_id]["VPID"] for amp_id in direct_amp_reasons if amp_id in amp_records
  )
  selected_amp_ids = set(direct_amp_reasons)
  selected_amp_ids.update(
    amp_id for amp_id, row in amp_records.items() if row["VPID"] in selected_vmp_ids
  )

  vmp_records = {
    row["VPID"]: row
    for row in _iter_archive_records(core_archive, "f_vmp2_", "VMP")
    if row.get("VPID") in selected_vmp_ids
  }
  selected_vtm_ids = {row["VTMID"] for row in vmp_records.values() if row.get("VTMID")}
  vtm_records = {
    row["VTMID"]: row
    for row in _iter_archive_records(core_archive, "f_vtm2_", "VTM")
    if row.get("VTMID") in selected_vtm_ids
  }

  vmpp_records = {
    row["VPPID"]: row
    for row in _iter_archive_records(core_archive, "f_vmpp2_", "VMPP")
    if row.get("VPID") in selected_vmp_ids
  }
  selected_vmpp_ids = set(vmpp_records)
  ampp_records = {
    row["APPID"]: row
    for row in _iter_archive_records(core_archive, "f_ampp2_", "AMPP")
    if row.get("APID") in selected_amp_ids or row.get("VPPID") in selected_vmpp_ids
  }

  vtm_ingredient_pairs, ingredient_member = _read_vtm_ingredients(bonus_archive, selected_vtm_ids)
  selected_ingredient_ids = {ingredient_id for _, ingredient_id in vtm_ingredient_pairs}
  ingredient_records = {
    row["ISID"]: row
    for row in _iter_archive_records(core_archive, "f_ingredient2_", "ING")
    if row.get("ISID") in selected_ingredient_ids
  }

  terms: list[dict[str, object]] = []
  relationships: list[dict[str, object]] = []
  for concept_id, row in vmp_records.items():
    classification = vmp_classes.get(concept_id, {})
    reason = direct_vmp_reasons.get(concept_id) or _reason_via_selected_amp(
      concept_id, selected_amp_ids, amp_records, direct_amp_reasons
    )
    terms.extend(_term_variants(row, concept_id, "VMP", reason, classification))
    if row.get("VTMID"):
      relationships.append(_relationship(concept_id, "VMP", "has_vtm", row["VTMID"], "VTM"))

  for concept_id, row in amp_records.items():
    if concept_id not in selected_amp_ids:
      continue
    classification = amp_classes.get(concept_id, {})
    reason = direct_amp_reasons.get(concept_id) or f"via_vmp:{row['VPID']}"
    terms.extend(_term_variants(row, concept_id, "AMP", reason, classification))
    relationships.append(_relationship(concept_id, "AMP", "has_vmp", row["VPID"], "VMP"))

  for concept_id, row in vmpp_records.items():
    reason = f"via_vmp:{row['VPID']}"
    terms.extend(_term_variants(row, concept_id, "VMPP", reason, {}))
    relationships.append(_relationship(concept_id, "VMPP", "has_vmp", row["VPID"], "VMP"))

  for concept_id, row in ampp_records.items():
    reason = f"via_amp:{row.get('APID', '')}"
    terms.extend(_term_variants(row, concept_id, "AMPP", reason, {}))
    if row.get("APID"):
      relationships.append(_relationship(concept_id, "AMPP", "has_amp", row["APID"], "AMP"))
    if row.get("VPPID"):
      relationships.append(_relationship(concept_id, "AMPP", "has_vmpp", row["VPPID"], "VMPP"))

  for concept_id, row in vtm_records.items():
    terms.extend(_term_variants(row, concept_id, "VTM", "via_selected_vmp", {}))
  for concept_id, row in ingredient_records.items():
    terms.extend(_term_variants(row, concept_id, "INGREDIENT", "via_selected_vtm", {}))
  for vtm_id, ingredient_id in vtm_ingredient_pairs:
    relationships.append(_relationship(vtm_id, "VTM", "has_ingredient", ingredient_id, "INGREDIENT"))

  terms.sort(key=lambda row: (str(row["entity_type"]), str(row["concept_id"]), str(row["term_type"])))
  relationships.sort(key=lambda row: (str(row["source_type"]), str(row["source_id"]), str(row["target_id"])))
  return DmdExtraction(
    term_rows=terms,
    relationship_rows=relationships,
    selected_vmp_ids=selected_vmp_ids,
    selected_amp_ids=selected_amp_ids,
    files_read=[str(core_archive), str(bonus_archive), bnf_member, ingredient_member],
  )


def _read_classifications(
  bonus_archive: Path,
) -> tuple[dict[str, dict[str, set[str]]], dict[str, dict[str, set[str]]], str]:
  member_name, data = _read_nested_zip_xml(bonus_archive, "BNF.zip", "f_bnf")
  vmp: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
  amp: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
  for tag, row in _iter_xml_records(io.BytesIO(data), {"VMP", "AMP"}):
    identifier = row.get("VPID") if tag == "VMP" else row.get("APID")
    if not identifier:
      continue
    target = vmp if tag == "VMP" else amp
    for field in ("BNF", "ATC"):
      value = row.get(field, "")
      if value and value.lower() != "n/a":
        target[identifier][field.lower()].add(value)
  return vmp, amp, member_name


def _read_vtm_ingredients(bonus_archive: Path, vtm_ids: set[str]) -> tuple[list[tuple[str, str]], str]:
  with tarfile.open(bonus_archive, "r:*") as archive:
    member = _find_member(archive, "f_vtm_ing1_")
    with _required_file(archive, member) as handle:
      pairs = [
        (row["VTMID"], row["ISID"])
        for _, row in _iter_xml_records(handle, {"VTM_ING"})
        if row.get("VTMID") in vtm_ids and row.get("ISID")
      ]
  return pairs, member.name


def _iter_archive_records(archive_path: Path, member_prefix: str, record_tag: str) -> Iterator[dict[str, str]]:
  with tarfile.open(archive_path, "r:*") as archive:
    member = _find_member(archive, member_prefix)
    with _required_file(archive, member) as handle:
      for _, row in _iter_xml_records(handle, {record_tag}):
        yield row


def _iter_xml_records(handle: BinaryIO, tags: set[str]) -> Iterator[tuple[str, dict[str, str]]]:
  for _, element in ET.iterparse(handle, events=("end",)):
    tag = _local_name(element.tag)
    if tag not in tags:
      continue
    row = {_local_name(child.tag): (child.text or "").strip() for child in element}
    yield tag, row
    element.clear()


def _read_nested_zip_xml(tar_path: Path, zip_suffix: str, xml_prefix: str) -> tuple[str, bytes]:
  with tarfile.open(tar_path, "r:*") as archive:
    zip_member = next(
      (member for member in archive.getmembers() if member.isfile() and member.name.endswith(zip_suffix)),
      None,
    )
    if zip_member is None:
      raise ValueError(f"No *{zip_suffix} member found in {tar_path}")
    with _required_file(archive, zip_member) as handle:
      zip_bytes = handle.read()
  with zipfile.ZipFile(io.BytesIO(zip_bytes)) as nested:
    xml_name = next((name for name in nested.namelist() if Path(name).name.startswith(xml_prefix)), None)
    if xml_name is None:
      raise ValueError(f"No {xml_prefix} XML found in {zip_member.name}")
    return f"{zip_member.name}!{xml_name}", nested.read(xml_name)


def _find_member(archive: tarfile.TarFile, basename_prefix: str) -> tarfile.TarInfo:
  member = next(
    (
      candidate
      for candidate in archive.getmembers()
      if candidate.isfile() and Path(candidate.name).name.startswith(basename_prefix)
    ),
    None,
  )
  if member is None:
    raise ValueError(f"No member beginning {basename_prefix!r} in {archive.name}")
  return member


def _required_file(archive: tarfile.TarFile, member: tarfile.TarInfo) -> BinaryIO:
  handle = archive.extractfile(member)
  if handle is None:
    raise ValueError(f"Could not read {member.name} from {archive.name}")
  return handle


def _local_name(tag: str) -> str:
  return tag.rsplit("}", 1)[-1]


def _selection_reasons(
  classifications: dict[str, set[str]],
  bnf_prefixes: tuple[str, ...],
  atc_prefixes: tuple[str, ...],
) -> str:
  reasons = []
  for code in sorted(classifications.get("bnf", ())):
    if code.startswith(bnf_prefixes):
      reasons.append(f"BNF:{code}")
  for code in sorted(classifications.get("atc", ())):
    if code.startswith(atc_prefixes):
      reasons.append(f"ATC:{code}")
  return "|".join(reasons)


def _reason_via_selected_amp(
  vmp_id: str,
  selected_amp_ids: set[str],
  amp_records: dict[str, dict[str, str]],
  direct_amp_reasons: dict[str, str],
) -> str:
  sources = [
    f"via_amp:{amp_id}:{direct_amp_reasons.get(amp_id, '')}"
    for amp_id in selected_amp_ids
    if amp_records.get(amp_id, {}).get("VPID") == vmp_id and amp_id in direct_amp_reasons
  ]
  return "|".join(sorted(sources)) or "via_related_product"


def _term_variants(
  row: dict[str, str],
  concept_id: str,
  entity_type: str,
  selection_basis: str,
  classification: dict[str, set[str]],
) -> list[dict[str, object]]:
  variants = []
  seen: set[str] = set()
  for field, term_type in (("NM", "name"), ("DESC", "description"), ("NM_PREV", "previous_name")):
    term = row.get(field, "").strip()
    if not term or term in seen:
      continue
    seen.add(term)
    variants.append({
      "concept_id": concept_id,
      "entity_type": entity_type,
      "term": term,
      "term_type": term_type,
      "is_current": not bool(row.get("INVALID")) and not bool(row.get("DISCCD")),
      "selection_basis": selection_basis,
      "bnf_codes": sorted(classification.get("bnf", ())),
      "atc_codes": sorted(classification.get("atc", ())),
    })
  return variants


def _relationship(
  source_id: str, source_type: str, relationship: str, target_id: str, target_type: str
) -> dict[str, str]:
  return {
    "source_id": source_id,
    "source_type": source_type,
    "relationship": relationship,
    "target_id": target_id,
    "target_type": target_type,
  }

