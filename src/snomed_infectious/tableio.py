from __future__ import annotations

import csv
import gzip
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def write_table(
  output_directory: Path,
  stem: str,
  columns: Sequence[str],
  rows: Iterable[Mapping[str, object]],
  output_format: str,
) -> tuple[Path, int]:
  """Write records as TSV, compressed TSV, or Parquet and return path and row count."""
  output_directory.mkdir(parents=True, exist_ok=True)
  if output_format == "parquet":
    return _write_parquet(output_directory / f"{stem}.parquet", columns, rows)

  suffix = ".tsv.gz" if output_format == "tsv.gz" else ".tsv"
  path = output_directory / f"{stem}{suffix}"
  opener = gzip.open if output_format == "tsv.gz" else open
  count = 0
  with opener(path, "wt", encoding="utf-8", newline="") as handle:
    writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t", extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
      writer.writerow({column: _scalar(row.get(column, "")) for column in columns})
      count += 1
  return path, count


def _write_parquet(
  path: Path,
  columns: Sequence[str],
  rows: Iterable[Mapping[str, object]],
) -> tuple[Path, int]:
  try:
    import pyarrow as pa
    import pyarrow.parquet as pq
  except ImportError as error:
    raise RuntimeError(
      "Parquet output requires pyarrow. Install with: python -m pip install '.[parquet]'"
    ) from error

  materialized = [{column: _scalar(row.get(column, "")) for column in columns} for row in rows]
  table = pa.Table.from_pylist(materialized)
  pq.write_table(table, path, compression="zstd")
  return path, len(materialized)


def _scalar(value: object) -> object:
  if isinstance(value, bool):
    return "1" if value else "0"
  if isinstance(value, (list, tuple, set)):
    return "|".join(str(item) for item in value)
  if value is None:
    return ""
  return value

