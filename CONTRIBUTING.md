# Contributing

Contributions and focused bug reports are welcome.

## Development setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
```

Keep Dashboard runtime, SSH/SFTP file operations, and direct URScript execution
as explicit, separate workflows. New behavior should include tests and must not
assume that URSim filesystem paths are portable to every physical controller.

Never commit robot credentials, private network details, proprietary programs,
or third-party URCap bundles.
