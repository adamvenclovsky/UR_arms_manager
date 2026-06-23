# Contributing

Contributions and focused bug reports are welcome.

## Development setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
python -m compileall -q src tests
python -m pip check
python -m ruff check .
```

Keep Dashboard runtime, SSH/SFTP file operations, and direct URScript execution
as explicit, separate workflows. New behavior should include tests and must not
assume that URSim filesystem paths are portable to every physical controller.

Never commit robot credentials, private network details, proprietary programs,
or third-party URCap bundles.

Tests must use fakes for Dashboard, RTDE, SSH/SFTP, and script sockets. Do not add a
test that discovers or contacts a configured robot. Any change to command gating,
remote paths, direct scripts, or Dashboard response handling needs a regression test.
