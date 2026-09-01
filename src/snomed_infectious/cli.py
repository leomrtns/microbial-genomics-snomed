from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .broad import BroadSnomedExtraction, discover_related_snomed
from .dmd import DmdExtraction, extract_dmd
from .tableio import write_table
from .wide import (
  DMD_ONLY_COLUMNS,
  SHARED_MATRIX_COLUMNS,
  SNOMED_ONLY_COLUMNS,
  add_snomed_source_release,
  make_dmd_wide_rows,
  matrix_column_descriptions,
  partition_vocabulary_matrices,
)


SCOPE_COLUMNS = (
  "include",
  "concept_id",
  "preferred_name",
  "fully_specified_name",
  "entity_category",
  "semantic_tag",
  "confidence",
  "why_included",
  "linked_disease_ids",
  "linked_diseases",
  "linked_microbe_ids",
  "linked_microbes",
  "relationship_summary",
  "active_term_count",
)


def build_parser() -> argparse.ArgumentParser:
  parser = argparse.ArgumentParser(
    prog="snomed-infectious",
    description="Build a broad, readable microbial-genomics terminology table from SNOMED CT UK and dm+d.",
  )
  parser.add_argument("--version", action="version", version=__version__)
  subparsers = parser.add_subparsers(dest="command", required=True)
  discover_parser = subparsers.add_parser(
    "discover-scope", help="Discover a reviewable SNOMED concept scope before extraction"
  )
  discover_parser.add_argument("--snomed-root", type=Path, required=True)
  discover_parser.add_argument("--output-dir", type=Path, required=True)
  _add_scope_options(discover_parser)

  extract_parser = subparsers.add_parser("extract", help="Build the three mutually exclusive matrices")
  extract_parser.add_argument("--snomed-root", type=Path, help="Decompressed SNOMED CT UK release root")
  extract_parser.add_argument("--dmd-archive", type=Path, help="dm+d core .txz archive")
  extract_parser.add_argument("--dmd-bonus-archive", type=Path, help="dm+d supplementary .txz archive")
  extract_parser.add_argument("--output-dir", type=Path, required=True)
  extract_parser.add_argument("--scope-file", type=Path, help="Edited scope_candidates.tsv from discover-scope")
  _add_scope_options(extract_parser)
  extract_parser.add_argument("--format", choices=("tsv", "tsv.gz", "parquet"), default="tsv.gz")
  return parser


def _add_scope_options(parser: argparse.ArgumentParser) -> None:
  parser.add_argument(
    "--profile",
    choices=("core", "research", "expansive"),
    default="research",
    help="Built-in breadth profile (default: research)",
  )
  parser.add_argument("--config", type=Path, help="Custom JSON configuration; overrides --profile")
  parser.add_argument(
    "--seed-concept", action="append", default=[], metavar="SCTID",
    help="Additional SNOMED concept root to include with all descendants; repeatable",
  )
  parser.add_argument(
    "--include-term", action="append", default=[], metavar="TEXT",
    help="Additional literal text to find in fully specified names; repeatable",
  )
  parser.add_argument(
    "--include-regex", action="append", default=[], metavar="REGEX",
    help="Additional regular expression for fully specified names; repeatable",
  )


def main(argv: list[str] | None = None) -> int:
  args = build_parser().parse_args(argv)
  if args.command == "discover-scope":
    return run_discover_scope(args)
  return run_extract(args)


def run_discover_scope(args: argparse.Namespace) -> int:
  _validate_paths(args.snomed_root, args.config)
  config, config_path = _load_config(args)
  args.output_dir.mkdir(parents=True, exist_ok=True)
  started = time.time()
  print(f"Discovering SNOMED scope with the {config['profile']['name']} profile...", file=sys.stderr)
  snomed = discover_related_snomed(args.snomed_root, config["snomed"])
  scope_rows = [{"include": True, **row} for row in snomed.candidate_rows]
  scope_path, scope_count = write_table(
    args.output_dir, "scope_candidates", SCOPE_COLUMNS, scope_rows, "tsv"
  )
  scope_manifest = {
    "title": "Editable SNOMED microbial scope",
    "description": (
      "Review scope_candidates.tsv and change include from 1 to 0 for concepts that should be excluded. "
      "Then pass the file to extract with --scope-file using the same profile and user seeds."
    ),
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "software": {"name": "microbial-genomics-snomed", "version": __version__},
    "elapsed_seconds": round(time.time() - started, 3),
    "profile": config["profile"],
    "resolved_config": str(config_path),
    "configuration": config,
    "scope_file": scope_path.name,
    "candidate_concepts": scope_count,
    "discovery_summary": snomed.summary,
    "columns": {
      "include": "User-editable: 1 includes the concept; 0 excludes it from final SNOMED matrices.",
      "concept_id": "SNOMED CT identifier.",
      "preferred_name": "GB English display name.",
      "confidence": "High for semantic discovery; medium for lexical-only discovery.",
      "why_included": "Auditable discovery evidence.",
    },
  }
  manifest_path = args.output_dir / "scope_manifest.json"
  manifest_path.write_text(json.dumps(scope_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  print(f"Wrote {scope_count:,} reviewable concepts to {scope_path}", file=sys.stderr)
  return 0


def run_extract(args: argparse.Namespace) -> int:
  _validate_args(args)
  config, config_path = _load_config(args)
  args.output_dir.mkdir(parents=True, exist_ok=True)
  started = time.time()
  inputs: list[str] = []
  snomed: BroadSnomedExtraction | None = None
  dmd: DmdExtraction | None = None
  wide_rows: list[dict[str, object]] = []
  table_metadata: dict[str, dict[str, object]] = {}

  if args.snomed_root:
    print("Discovering SNOMED concepts across microbial and clinical hierarchies...", file=sys.stderr)
    snomed = discover_related_snomed(args.snomed_root, config["snomed"])
    add_snomed_source_release(snomed.term_rows, args.snomed_root)
    snomed_rows = snomed.term_rows
    if args.scope_file:
      approved_ids = _load_approved_scope(args.scope_file)
      available_ids = {str(row["concept_id"]) for row in snomed_rows}
      missing_ids = approved_ids - available_ids
      if missing_ids:
        sample = ", ".join(sorted(missing_ids, key=int)[:10])
        raise ValueError(
          f"{len(missing_ids)} approved scope concepts were not rediscovered; use the same profile/seeds. "
          f"Examples: {sample}"
        )
      snomed_rows = [row for row in snomed_rows if str(row["concept_id"]) in approved_ids]
    wide_rows.extend(snomed_rows)
    inputs.extend(snomed.files_read)

  if args.dmd_archive:
    print("Extracting and denormalising dm+d anti-infective medicines...", file=sys.stderr)
    dmd_config = config["dmd"]
    dmd = extract_dmd(
      args.dmd_archive,
      args.dmd_bonus_archive,
      tuple(dmd_config.get("bnf_prefixes", ())),
      tuple(dmd_config.get("atc_prefixes", ())),
    )
    wide_rows.extend(make_dmd_wide_rows(dmd, args.dmd_archive))
    inputs.extend(dmd.files_read)

  wide_rows.sort(
    key=lambda row: (
      str(row.get("vocabulary", "")),
      str(row.get("entity_category", "")),
      str(row.get("concept_id", "")),
      str(row.get("term", "")),
    )
  )
  snomed_only_rows, dmd_only_rows, shared_rows, overlap = partition_vocabulary_matrices(wide_rows)
  if snomed_only_rows:
    snomed_path, snomed_count = write_table(
      args.output_dir, "snomed_only_terms", SNOMED_ONLY_COLUMNS, snomed_only_rows, args.format
    )
    table_metadata["snomed_only_terms"] = {
      "file": snomed_path.name,
      "rows": snomed_count,
      "description": "SNOMED CT UK term rows whose concept identifiers do not occur in the dm+d matrix.",
    }
  if dmd_only_rows:
    dmd_path, dmd_count = write_table(
      args.output_dir, "nhsbsa_dmd_only_terms", DMD_ONLY_COLUMNS, dmd_only_rows, args.format
    )
    table_metadata["nhsbsa_dmd_only_terms"] = {
      "file": dmd_path.name,
      "rows": dmd_count,
      "description": "NHSBSA dm+d term rows whose concept identifiers do not occur in the SNOMED matrix.",
    }
  if shared_rows:
    shared_path, shared_count = write_table(
      args.output_dir, "shared_snomed_dmd_concepts", SHARED_MATRIX_COLUMNS, shared_rows, args.format
    )
    table_metadata["shared_snomed_dmd_concepts"] = {
      "file": shared_path.name,
      "rows": shared_count,
      "description": "One fully denormalised row for each concept identifier present in both vocabularies.",
    }
  manifest = _manifest(
    args, config, config_path, table_metadata, wide_rows, overlap, snomed, dmd, inputs, started
  )
  manifest_path = args.output_dir / "manifest.json"
  manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
  print(
    f"Wrote {len(snomed_only_rows):,} SNOMED-only rows, {len(dmd_only_rows):,} dm+d-only rows, "
    f"and {len(shared_rows):,} shared concepts",
    file=sys.stderr,
  )
  return 0


def _validate_args(args: argparse.Namespace) -> None:
  if not args.snomed_root and not args.dmd_archive:
    raise SystemExit("Provide --snomed-root, --dmd-archive, or both")
  if bool(args.dmd_archive) != bool(args.dmd_bonus_archive):
    raise SystemExit("dm+d extraction requires both --dmd-archive and --dmd-bonus-archive")
  _validate_paths(args.snomed_root, args.dmd_archive, args.dmd_bonus_archive, args.config, args.scope_file)


def _validate_paths(*paths: Path | None) -> None:
  for path in paths:
    if path and not path.exists():
      raise SystemExit(f"Input does not exist: {path}")


def _load_config(args: argparse.Namespace) -> tuple[dict[str, object], Path]:
  config_path = args.config or Path(__file__).parents[2] / "configs" / f"{args.profile}.json"
  config = json.loads(config_path.read_text(encoding="utf-8"))
  hierarchy_roots = config["snomed"]["hierarchy_roots"]
  lexical_rules = config["snomed"]["lexical_rules"]
  for concept_id in args.seed_concept:
    if not concept_id.isdigit():
      raise SystemExit(f"--seed-concept must be numeric: {concept_id}")
    hierarchy_roots[f"user seed {concept_id}"] = [concept_id]
  for index, term in enumerate(args.include_term, start=1):
    lexical_rules[f"user literal term {index}: {term}"] = re.escape(term)
  for index, pattern in enumerate(args.include_regex, start=1):
    try:
      re.compile(pattern)
    except re.error as error:
      raise SystemExit(f"Invalid --include-regex {pattern!r}: {error}") from error
    lexical_rules[f"user regular expression {index}"] = pattern
  config["user_additions"] = {
    "seed_concepts": list(args.seed_concept),
    "literal_terms": list(args.include_term),
    "regular_expressions": list(args.include_regex),
  }
  return config, config_path


def _load_approved_scope(path: Path) -> set[str]:
  opener = gzip.open if path.suffix == ".gz" else open
  with opener(path, "rt", encoding="utf-8-sig", newline="") as handle:
    reader = csv.DictReader(handle, delimiter="\t", quoting=csv.QUOTE_NONE)
    if not reader.fieldnames or "concept_id" not in reader.fieldnames or "include" not in reader.fieldnames:
      raise ValueError("Scope file must contain concept_id and include columns")
    return {
      row["concept_id"]
      for row in reader
      if row.get("include", "").strip().lower() in {"1", "true", "yes", "y"}
    }


def _manifest(
  args: argparse.Namespace,
  config: dict[str, object],
  config_path: Path,
  tables: dict[str, dict[str, object]],
  wide_rows: list[dict[str, object]],
  overlap: dict[str, object],
  snomed: BroadSnomedExtraction | None,
  dmd: DmdExtraction | None,
  inputs: list[str],
  started: float,
) -> dict[str, object]:
  vocabulary_counts = Counter(str(row["vocabulary"]) for row in wide_rows)
  category_counts = Counter(str(row["entity_category"]) for row in wide_rows)
  confidence_counts = Counter(str(row["confidence"]) for row in wide_rows)
  total_output_bytes = sum(
    (args.output_dir / str(metadata["file"])).stat().st_size for metadata in tables.values()
  )
  return {
    "title": "Broad microbial and infectious-disease terminology matrices",
    "description": (
      "Three mutually exclusive, human-readable matrices for microbial-genomics mapping: SNOMED-only terms, "
      "NHSBSA dm+d-only terms, and one wide row per concept identifier observed in both vocabularies."
    ),
    "purpose": (
      "Terminology matching and database linkage by microbial genomics researchers; this is not a clinical "
      "decision-support dataset."
    ),
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "software": {"name": "microbial-genomics-snomed", "version": __version__},
    "elapsed_seconds": round(time.time() - started, 3),
    "output_format": args.format,
    "breadth_profile": config["profile"],
    "resolved_config": str(config_path),
    "approved_scope_file": str(args.scope_file) if args.scope_file else None,
    "output_bytes_excluding_manifest": total_output_bytes,
    "selection_method": {
      "phase_1_discovery": [
        "All active descendants of configured infectious-disease, microbial, vaccine, and microbiology roots.",
        "Concepts with defining SNOMED relationships to a scoped disease or microbe, plus their descendants.",
        "Additional active concepts whose fully specified names match explicit microbial lexical rules.",
        "dm+d products classified by configured BNF or ATC prefixes, expanded through product and ingredient links.",
      ],
      "phase_2_denormalisation_and_split": (
        "Names and relevant links are joined into readable columns. Non-overlapping identifiers go to separate "
        "SNOMED-only and dm+d-only matrices; shared identifiers go only to a third, wider matrix."
      ),
      "polyhierarchy": (
        "All active inferred IS-A parents are traversed. A concept is included when any parent path reaches a "
        "configured root, so organ-system infections such as urinary or respiratory infections are retained."
      ),
    },
    "caveats": [
      "Related is broader than descendant-of infectious disease; medium-confidence lexical-only rows may need review.",
      "Direct SNOMED relationships are not equivalent to epidemiological proof and may not encode every association.",
      "dm+d BNF/ATC class membership is not a patient-specific indication.",
      "Inactive SNOMED descriptions are excluded; dm+d historical names are retained and current status is flagged.",
      "Generated content remains subject to SNOMED CT and dm+d licensing conditions.",
    ],
    "tables": tables,
    "matrix_data_dictionaries": {
      "snomed_only_terms": matrix_column_descriptions(SNOMED_ONLY_COLUMNS),
      "nhsbsa_dmd_only_terms": matrix_column_descriptions(DMD_ONLY_COLUMNS),
      "shared_snomed_dmd_concepts": matrix_column_descriptions(SHARED_MATRIX_COLUMNS),
    },
    "cross_vocabulary_overlap": overlap,
    "row_counts": {
      "by_vocabulary": dict(sorted(vocabulary_counts.items())),
      "by_entity_category": dict(sorted(category_counts.items())),
      "by_confidence": dict(sorted(confidence_counts.items())),
    },
    "snomed_discovery_summary": snomed.summary if snomed else None,
    "dmd_discovery_summary": (
      {
        "selected_vmp_concepts": len(dmd.selected_vmp_ids),
        "selected_amp_concepts": len(dmd.selected_amp_ids),
        "term_rows": len(dmd.term_rows),
      }
      if dmd else None
    ),
    "configuration": config,
    "inputs_read_only": sorted(set(inputs)),
  }


if __name__ == "__main__":
  raise SystemExit(main())
