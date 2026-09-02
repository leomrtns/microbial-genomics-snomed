# Contributing

This is just so I'm not accepting contributions ATM. 
However, one thing I can say is "quod gratis asseritur, gratis negatur".
That is, if your pet LLM suggested a lot of changes without your close attention
I'll reject them. 

## Development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

Changes to discovery breadth must be auditable. 
Add or update tests.
Ensure new inclusion rules appear in `why_included` and the generated manifest.

