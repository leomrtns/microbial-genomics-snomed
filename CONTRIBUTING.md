# Contributing

Contributions are welcome through issues and pull requests.

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Keep source lines near 120 columns and use two spaces for indentation. Tests must use synthetic terminology fixtures: never commit SNOMED CT, dm+d, generated licensed extracts, or local source paths.

Changes to discovery breadth must be auditable. Add or update tests and ensure new inclusion rules appear in `why_included` and the generated manifest.

