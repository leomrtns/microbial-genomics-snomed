Merging information between Electronic Health Records (EHR) and microbial-genomics databases. At the moment only
[reference files from NHS](https://isd.digital.nhs.uk/trud) are supported.

# Broad microbial terminology extractor

This command-line program builds a small, readable vocabulary for microbial-genomics database matching from SNOMED CT UK
and NHS dm+d. It reads the licensed source releases in place and never modifies or unpacks them.

The deliverable consists of **three mutually exclusive matrices** (or `.tsv`/`.parquet`):

- `snomed_only_terms.tsv.gz` contains SNOMED CT UK identifiers absent from the selected dm+d scope.
- `nhsbsa_dmd_only_terms.tsv.gz` contains dm+d identifiers absent from the selected SNOMED scope.
- `shared_snomed_dmd_concepts.tsv.gz` contains one wider row for each identifier present in both vocabularies.

Together they cover:

- infectious diseases and organ-system infections;
- bacteria, fungi, viruses, protozoa, prions, archaea, and other causative agents;
- microbiology laboratory tests and observables;
- microbial procedures, specimens, substances, findings, and related concepts;
- vaccines and immunisation concepts;
- dm+d anti-infective therapeutic moieties, ingredients, generic products, branded products, and packs.

No join is required to interpret any matrix. The shared matrix contains both vocabularies' names, categories,
relationships, medicine hierarchy, ingredients, and classifications on the same row. Shared identifiers are excluded
from both “only” matrices.

## How “related” is discovered

A single SNOMED root cannot represent everything related to infection because diseases, organisms, tests, specimens,
procedures, vaccines, and products occupy different hierarchies. The program therefore uses two internal phases.

### Phase 1: broad discovery

1. Follow every active inferred `IS-A` edge below configured roots for infectious disease, microbial taxonomies, vaccine
products, and microbiology tests/procedures.
2. Include concepts with defining SNOMED relationships to a selected disease, microbe, or infectious agent, plus their
descendants.
3. Include direct causative agents of infectious diseases. This captures agents outside the narrow microbial taxonomy
without expanding a broad agent such as “organism” into unrelated plants and animals.
4. Add legacy or weakly modelled concepts whose fully specified names match explicit microbial lexical rules.
5. Select dm+d anti-infective products using the supplementary BNF/ATC mappings, then follow the dm+d product and
ingredient hierarchy.

Semantic and classification selections have `confidence=high`. Concepts found only by their name have
`confidence=medium` so they can be reviewed or filtered without hiding how they entered the table.

### Phase 2: denormalisation

Technical edges are converted to readable columns. For example, instead of a row such as `AMP -> has_vmp ->
41954511000001101`, the dm+d-only and shared matrices provide columns such as:

- `medicine_level = branded or manufacturer medicinal product`
- `generic_product_ids`
- `generic_products`
- `therapeutic_moieties`
- `ingredients`
- `bnf_codes` and `atc_codes`

The SNOMED-only and shared matrices likewise have `linked_diseases`, `linked_microbes`, `relationship_summary`, and
`why_included` columns. The partition avoids structurally blank dm+d columns on SNOMED-only rows and vice versa.

## Polyhierarchy

The traversal uses **all active inferred parents**, not one preferred parent. A urinary tract infection or infectious
pneumonia is included if any `IS-A` path reaches infectious disease, even when another path also places it under urinary
or respiratory disease.

Polyhierarchy does not connect different semantic domains. An antibiotic, vaccine, or laboratory test cannot be reached
through the infectious-disease root because it is not a disorder. The additional roots and relationship/lexical
discovery steps are what include those concepts.

## Install

Python 3.10 or later is required. Compressed and plain TSV need no third-party dependency.

```bash python3 -m venv .venv .venv/bin/python -m pip install -e . ```

For Parquet:

```
bash .venv/bin/python -m pip install -e '.[parquet]' 
```

No system-wide installation or `sudo` is needed.

## Choose the breadth

Breadth is an explicit input, not a fixed property of the software.

| Profile | Intended use | Included scope | |---|---|---| | `core` | High-specificity linkage | Infectious disorders,
microbial taxonomies, direct causative agents, and narrowly classified systemic anti-infectives. | | `research` |
Default microbial-genomics work | Core plus laboratory tests, all specimens, vaccines, transmission modes, antimicrobial
resistance, molecular diagnostics, infection control, public health, and broader anti-infectives. | | `expansive` |
High-recall exploration | Research plus broader symptoms/signs, exposure, hosts, reservoirs, vectors, virulence,
epidemiology, and genomic terminology. More manual review is expected. |

The profiles are ordinary JSON files in `configs/`. A study can copy one, change roots, regular expressions, BNF
prefixes, or ATC prefixes, and pass it using `--config`.

Users can also extend any profile from the command line:

```bash --seed-concept 123456789       # include this SCTID and all descendants --include-term "biofilm"       # literal
text in fully specified names --include-regex "plasmid|transposon|resistome" ```

Repeat any of these options as needed. Every addition is stored in the scope manifest and final manifest.

## Recommended two-stage workflow

First discover the candidate scope:

```bash .venv/bin/snomed-infectious discover-scope \ --snomed-root
/home/leo/Academic/UoL/103.CPRD/uk_sct2cl_42.2.0_20260603000001Z \ --profile research \ --output-dir scope/research ```

This writes an editable `scope_candidates.tsv` with one row per SNOMED concept. The `why_included` and `confidence`
columns explain the evidence. Change `include` from `1` to `0` for unwanted concepts.

Then build the final matrices from the approved scope:

```bash .venv/bin/snomed-infectious extract \ --snomed-root
/home/leo/Academic/UoL/103.CPRD/uk_sct2cl_42.2.0_20260603000001Z \ --dmd-archive
/home/leo/Academic/UoL/103.CPRD/nhsbsa_dmd_7.2.0_20260720000001.txz \ --dmd-bonus-archive
/home/leo/Academic/UoL/103.CPRD/nhsbsa_dmdbonus_7.2.0_20260720000001.txz \ --profile research \ --scope-file
scope/research/scope_candidates.tsv \ --output-dir outputs/2026-07-matrices \ --format tsv.gz ```

Use the same profile, seed concepts, literal terms, and regular expressions in both commands. The build refuses an
incompatible scope rather than silently dropping approved concepts.

## One-stage run

For an automatic, unreviewed extract, omit `discover-scope` and `--scope-file`:

```bash .venv/bin/snomed-infectious extract \ --snomed-root
/home/leo/Academic/UoL/103.CPRD/uk_sct2cl_42.2.0_20260603000001Z \ --dmd-archive
/home/leo/Academic/UoL/103.CPRD/nhsbsa_dmd_7.2.0_20260720000001.txz \ --dmd-bonus-archive
/home/leo/Academic/UoL/103.CPRD/nhsbsa_dmdbonus_7.2.0_20260720000001.txz \ --profile research \ --output-dir
outputs/2026-07-matrices \ --format tsv.gz ```

Run directly from the source tree without installation:

```bash PYTHONPATH=src python3 -m snomed_infectious extract \ --snomed-root /path/to/decompressed/snomed-release \
--dmd-archive /path/to/nhsbsa_dmd_release.txz \ --dmd-bonus-archive /path/to/nhsbsa_dmdbonus_release.txz \ --output-dir
outputs/latest ```

Use `--format tsv` for uncompressed TSV or `--format parquet` after installing `pyarrow`.

## Matrix structure

Each matrix has one row per searchable term. Repetition is intentional: a concept with one fully specified name and
three synonyms occupies four rows. Every row repeats the readable context needed to use it without reconstructing SNOMED
or dm+d.

Important columns include:

| Column | Meaning | |---|---| | `entity_category` | Plain-language type such as microbe, infectious condition,
laboratory test, vaccine, or medicine. | | `concept_id` | Stable source identifier stored as text. | | `preferred_name`
| Best display name for the concept. | | `term` | A searchable name or synonym. | | `confidence` | `high` for semantic
selection; `medium` for lexical-only discovery. | | `why_included` | Exact, human-readable reason the concept entered
the scope. | | `linked_diseases` | Directly linked infectious diseases, when modelled. | | `linked_microbes` | Directly
linked microbes or causative agents, when modelled. | | `relationship_summary` | Readable relationship descriptions
rather than raw edge codes. | | `medicine_level` | Ingredient, therapeutic moiety, generic/branded product, or pack. | |
`generic_products`, `brand_products`, `ingredients` | Denormalised dm+d hierarchy names. | | `bnf_codes`, `atc_codes` |
Medicine classification evidence. |

The dm+d matrix additionally contains its flattened medicine hierarchy. The SNOMED matrix contains semantic tags and
disease/microbe relationships. Each has an independent data dictionary in `manifest.json`.

## Manifest

The manifest is intended to be sufficient documentation for a shared extract. It records:

- purpose and full scope description;
- both discovery phases;
- explicit polyhierarchy behaviour;
- caveats and licensing reminder;
- both matrices and their row counts;
- counts by vocabulary, category, and confidence;
- a complete data dictionary for each matrix;
- all configured roots, lexical rules, and medicine class prefixes;
- read-only source files and software version.

## What else can be considered “microbial-related”?

The default research profile covers the commonly requested groups:

- organisms and infectious agents;
- infectious disorders, including organ-system polyhierarchy;
- laboratory tests and observables;
- specimens;
- vaccines and immunisation;
- anti-infective dm+d medicines;
- infection-control procedures;
- antimicrobial resistance and susceptibility;
- molecular diagnostics, culture, and sequencing;
- transmission modes;
- public-health notification, outbreak, and contact-tracing concepts.

The expansive profile also explores signs and symptoms, hosts, reservoirs, vectors, exposures, virulence, toxins, and
epidemiology. These are less specific: fever and cough are relevant to infection but are not uniquely microbial.

Other defensible discovery approaches can be added later or used to supply seeds to this software:

1. Curated reference sets or ECL queries from a SNOMED terminology server.
2. External authoritative lists such as notifiable diseases, pathogen taxonomies, antimicrobial classifications, or
laboratory catalogues.
3. Controlled graph-neighbourhood expansion by relationship type and hop count.
4. Mapping from microbial databases first, using organism names, taxonomic identifiers, resistance genes, virulence
factors, and assay names as seeds.
5. Corpus-based discovery from clinical/laboratory text, followed by expert review.
6. Embedding or language-model similarity as a candidate generator, never as unexplained automatic inclusion.

The key design rule is that each method should emit evidence into `why_included`, keeping breadth reviewable and
reproducible.

## Scope customisation

All semantic roots and lexical rules are in `configs/core.json`, `configs/research.json`, and `configs/expansive.json`.
Copy a file, edit it, and pass the copy with `--config`. This is preferable to changing Python source and makes a
study-specific scope reproducible.

The default dm+d rules include BNF chapter `05` and systemic, topical, ophthalmic, otological, genitourinary,
intestinal, antiparasitic, immune-serum, and vaccine ATC classes. Narrow the ATC prefixes if the study needs only
therapeutic systemic anti-infectives.

## Important limitations

- No finite terminology rule can guarantee every scientifically plausible association. The table records explicit
  semantics and lexical evidence rather than pretending that “related” is objective.
- Medium-confidence lexical-only concepts should be reviewed for a high-specificity analysis.
- A terminology relationship is not evidence of causality or clinical indication.
- dm+d BNF/ATC classification is not a patient-specific indication.
- The software includes no licensed terminology content, but generated tables remain subject to SNOMED CT and dm+d
  licensing conditions.

## Test

```bash PYTHONPATH=src python3 -m unittest discover -s tests -v ```

The tests cover polyhierarchy, cross-hierarchy laboratory and vaccine selection, RF2 parsing, dm+d class selection, wide
product/ingredient denormalisation, and the cross-vocabulary split.

## References

- [SNOMED CT Release File
  Specification](https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4-component-release-files-specification)
- [SNOMED CT release types and Snapshot
  definition](https://docs.snomed.org/snomed-ct-practical-guides/snomed-ct-starter-guide/13-release-schedule-and-file-formats)
- [NHS England dm+d model](https://digital.nhs.uk/services/terminology-and-classifications/dm-d)
- [NHSBSA dm+d release and supplementary files](https://www.nhsbsa.nhs.uk/cy/node/14056)

# Broad microbial terminology extractor

This command-line program builds a small, readable vocabulary for microbial-genomics database matching from SNOMED CT UK
and NHS dm+d. It reads the licensed source releases in place and never modifies or unpacks them.

The deliverable consists of **three mutually exclusive matrices** (or `.tsv`/`.parquet`):

- `snomed_only_terms.tsv.gz` contains SNOMED CT UK identifiers absent from the selected dm+d scope.
- `nhsbsa_dmd_only_terms.tsv.gz` contains dm+d identifiers absent from the selected SNOMED scope.
- `shared_snomed_dmd_concepts.tsv.gz` contains one wider row for each identifier present in both vocabularies.

Together they cover:

- infectious diseases and organ-system infections;
- bacteria, fungi, viruses, protozoa, prions, archaea, and other causative agents;
- microbiology laboratory tests and observables;
- microbial procedures, specimens, substances, findings, and related concepts;
- vaccines and immunisation concepts;
- dm+d anti-infective therapeutic moieties, ingredients, generic products, branded products, and packs.

No join is required to interpret any matrix. The shared matrix contains both vocabularies' names, categories,
relationships, medicine hierarchy, ingredients, and classifications on the same row. Shared identifiers are excluded
from both “only” matrices.

## How “related” is discovered

A single SNOMED root cannot represent everything related to infection because diseases, organisms, tests, specimens,
procedures, vaccines, and products occupy different hierarchies. The program therefore uses two internal phases.

### Phase 1: broad discovery

1. Follow every active inferred `IS-A` edge below configured roots for infectious disease, microbial taxonomies, vaccine
products, and microbiology tests/procedures.
2. Include concepts with defining SNOMED relationships to a selected disease, microbe, or infectious agent, plus their
descendants.
3. Include direct causative agents of infectious diseases. This captures agents outside the narrow microbial taxonomy
without expanding a broad agent such as “organism” into unrelated plants and animals.
4. Add legacy or weakly modelled concepts whose fully specified names match explicit microbial lexical rules.
5. Select dm+d anti-infective products using the supplementary BNF/ATC mappings, then follow the dm+d product and
ingredient hierarchy.

Semantic and classification selections have `confidence=high`. Concepts found only by their name have
`confidence=medium` so they can be reviewed or filtered without hiding how they entered the table.

### Phase 2: denormalisation

Technical edges are converted to readable columns. For example, instead of a row such as `AMP -> has_vmp ->
41954511000001101`, the dm+d-only and shared matrices provide columns such as:

- `medicine_level = branded or manufacturer medicinal product`
- `generic_product_ids`
- `generic_products`
- `therapeutic_moieties`
- `ingredients`
- `bnf_codes` and `atc_codes`

The SNOMED-only and shared matrices likewise have `linked_diseases`, `linked_microbes`, `relationship_summary`, and
`why_included` columns. The partition avoids structurally blank dm+d columns on SNOMED-only rows and vice versa.

## Polyhierarchy

The traversal uses **all active inferred parents**, not one preferred parent. A urinary tract infection or infectious
pneumonia is included if any `IS-A` path reaches infectious disease, even when another path also places it under urinary
or respiratory disease.

Polyhierarchy does not connect different semantic domains. An antibiotic, vaccine, or laboratory test cannot be reached
through the infectious-disease root because it is not a disorder. The additional roots and relationship/lexical
discovery steps are what include those concepts.

## Install

Python 3.10 or later is required. Compressed and plain TSV need no third-party dependency.

```bash python3 -m venv .venv .venv/bin/python -m pip install -e . ```

For Parquet:

```bash .venv/bin/python -m pip install -e '.[parquet]' ```

No system-wide installation or `sudo` is needed.

## Choose the breadth

Breadth is an explicit input, not a fixed property of the software.

| Profile | Intended use | Included scope | |---|---|---| | `core` | High-specificity linkage | Infectious disorders,
microbial taxonomies, direct causative agents, and narrowly classified systemic anti-infectives. | | `research` |
Default microbial-genomics work | Core plus laboratory tests, all specimens, vaccines, transmission modes, antimicrobial
resistance, molecular diagnostics, infection control, public health, and broader anti-infectives. | | `expansive` |
High-recall exploration | Research plus broader symptoms/signs, exposure, hosts, reservoirs, vectors, virulence,
epidemiology, and genomic terminology. More manual review is expected. |

The profiles are ordinary JSON files in `configs/`. A study can copy one, change roots, regular expressions, BNF
prefixes, or ATC prefixes, and pass it using `--config`.

Users can also extend any profile from the command line:

```bash --seed-concept 123456789       # include this SCTID and all descendants --include-term "biofilm"       # literal
text in fully specified names --include-regex "plasmid|transposon|resistome" ```

Repeat any of these options as needed. Every addition is stored in the scope manifest and final manifest.

## Recommended two-stage workflow

First discover the candidate scope:

```bash .venv/bin/snomed-infectious discover-scope \ --snomed-root
/home/leo/Academic/UoL/103.CPRD/uk_sct2cl_42.2.0_20260603000001Z \ --profile research \ --output-dir scope/research ```

This writes an editable `scope_candidates.tsv` with one row per SNOMED concept. The `why_included` and `confidence`
columns explain the evidence. Change `include` from `1` to `0` for unwanted concepts.

Then build the final matrices from the approved scope:

```bash .venv/bin/snomed-infectious extract \ --snomed-root
/home/leo/Academic/UoL/103.CPRD/uk_sct2cl_42.2.0_20260603000001Z \ --dmd-archive
/home/leo/Academic/UoL/103.CPRD/nhsbsa_dmd_7.2.0_20260720000001.txz \ --dmd-bonus-archive
/home/leo/Academic/UoL/103.CPRD/nhsbsa_dmdbonus_7.2.0_20260720000001.txz \ --profile research \ --scope-file
scope/research/scope_candidates.tsv \ --output-dir outputs/2026-07-matrices \ --format tsv.gz ```

Use the same profile, seed concepts, literal terms, and regular expressions in both commands. The build refuses an
incompatible scope rather than silently dropping approved concepts.

## One-stage run

For an automatic, unreviewed extract, omit `discover-scope` and `--scope-file`:

```bash .venv/bin/snomed-infectious extract \ --snomed-root
/home/leo/Academic/UoL/103.CPRD/uk_sct2cl_42.2.0_20260603000001Z \ --dmd-archive
/home/leo/Academic/UoL/103.CPRD/nhsbsa_dmd_7.2.0_20260720000001.txz \ --dmd-bonus-archive
/home/leo/Academic/UoL/103.CPRD/nhsbsa_dmdbonus_7.2.0_20260720000001.txz \ --profile research \ --output-dir
outputs/2026-07-matrices \ --format tsv.gz ```

Run directly from the source tree without installation:

```bash PYTHONPATH=src python3 -m snomed_infectious extract \ --snomed-root /path/to/decompressed/snomed-release \
--dmd-archive /path/to/nhsbsa_dmd_release.txz \ --dmd-bonus-archive /path/to/nhsbsa_dmdbonus_release.txz \ --output-dir
outputs/latest ```

Use `--format tsv` for uncompressed TSV or `--format parquet` after installing `pyarrow`.

## Matrix structure

Each matrix has one row per searchable term. Repetition is intentional: a concept with one fully specified name and
three synonyms occupies four rows. Every row repeats the readable context needed to use it without reconstructing SNOMED
or dm+d.

Important columns include:

| Column | Meaning | |---|---| | `entity_category` | Plain-language type such as microbe, infectious condition,
laboratory test, vaccine, or medicine. | | `concept_id` | Stable source identifier stored as text. | | `preferred_name`
| Best display name for the concept. | | `term` | A searchable name or synonym. | | `confidence` | `high` for semantic
selection; `medium` for lexical-only discovery. | | `why_included` | Exact, human-readable reason the concept entered
the scope. | | `linked_diseases` | Directly linked infectious diseases, when modelled. | | `linked_microbes` | Directly
linked microbes or causative agents, when modelled. | | `relationship_summary` | Readable relationship descriptions
rather than raw edge codes. | | `medicine_level` | Ingredient, therapeutic moiety, generic/branded product, or pack. | |
`generic_products`, `brand_products`, `ingredients` | Denormalised dm+d hierarchy names. | | `bnf_codes`, `atc_codes` |
Medicine classification evidence. |

The dm+d matrix additionally contains its flattened medicine hierarchy. The SNOMED matrix contains semantic tags and
disease/microbe relationships. Each has an independent data dictionary in `manifest.json`.

## Manifest

The manifest is intended to be sufficient documentation for a shared extract. It records:

- purpose and full scope description;
- both discovery phases;
- explicit polyhierarchy behaviour;
- caveats and licensing reminder;
- both matrices and their row counts;
- counts by vocabulary, category, and confidence;
- a complete data dictionary for each matrix;
- all configured roots, lexical rules, and medicine class prefixes;
- read-only source files and software version.

## What else can be considered “microbial-related”?

The default research profile covers the commonly requested groups:

- organisms and infectious agents;
- infectious disorders, including organ-system polyhierarchy;
- laboratory tests and observables;
- specimens;
- vaccines and immunisation;
- anti-infective dm+d medicines;
- infection-control procedures;
- antimicrobial resistance and susceptibility;
- molecular diagnostics, culture, and sequencing;
- transmission modes;
- public-health notification, outbreak, and contact-tracing concepts.

The expansive profile also explores signs and symptoms, hosts, reservoirs, vectors, exposures, virulence, toxins, and
epidemiology. These are less specific: fever and cough are relevant to infection but are not uniquely microbial.

Other defensible discovery approaches can be added later or used to supply seeds to this software:

1. Curated reference sets or ECL queries from a SNOMED terminology server.
2. External authoritative lists such as notifiable diseases, pathogen taxonomies, antimicrobial classifications, or
laboratory catalogues.
3. Controlled graph-neighbourhood expansion by relationship type and hop count.
4. Mapping from microbial databases first, using organism names, taxonomic identifiers, resistance genes, virulence
factors, and assay names as seeds.
5. Corpus-based discovery from clinical/laboratory text, followed by expert review.
6. Embedding or language-model similarity as a candidate generator, never as unexplained automatic inclusion.

The key design rule is that each method should emit evidence into `why_included`, keeping breadth reviewable and
reproducible.

## Scope customisation

All semantic roots and lexical rules are in `configs/core.json`, `configs/research.json`, and `configs/expansive.json`.
Copy a file, edit it, and pass the copy with `--config`. This is preferable to changing Python source and makes a
study-specific scope reproducible.

The default dm+d rules include BNF chapter `05` and systemic, topical, ophthalmic, otological, genitourinary,
intestinal, antiparasitic, immune-serum, and vaccine ATC classes. Narrow the ATC prefixes if the study needs only
therapeutic systemic anti-infectives.

## Important limitations

- No finite terminology rule can guarantee every scientifically plausible association. The table records explicit
  semantics and lexical evidence rather than pretending that “related” is objective.
- Medium-confidence lexical-only concepts should be reviewed for a high-specificity analysis.
- A terminology relationship is not evidence of causality or clinical indication.
- dm+d BNF/ATC classification is not a patient-specific indication.
- The software includes no licensed terminology content, but generated tables remain subject to SNOMED CT and dm+d
  licensing conditions.

## Test

```bash PYTHONPATH=src python3 -m unittest discover -s tests -v ```

The tests cover polyhierarchy, cross-hierarchy laboratory and vaccine selection, RF2 parsing, dm+d class selection, wide
product/ingredient denormalisation, and the cross-vocabulary split.

## References

- [SNOMED CT Release File
  Specification](https://docs.snomed.org/snomed-ct-specifications/snomed-ct-release-file-specification/component-release-file-specification/4-component-release-files-specification)
- [SNOMED CT release types and Snapshot
  definition](https://docs.snomed.org/snomed-ct-practical-guides/snomed-ct-starter-guide/13-release-schedule-and-file-formats)
- [NHS England dm+d model](https://digital.nhs.uk/services/terminology-and-classifications/dm-d)
- [NHSBSA dm+d release and supplementary files](https://www.nhsbsa.nhs.uk/cy/node/14056)
