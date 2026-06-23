# UR Arms Manager

![CI](https://github.com/BiggHughJass/UR_arms_manager/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-alpha-orange)

Web and command-line management for a small fleet of Universal Robots arms. The
project combines Dashboard control, RTDE monitoring, SSH/SFTP file management,
direct URScript execution, and a filesystem-based program library behind a
FastAPI/Jinja operator interface.

The development environment runs two isolated URSim controllers in Docker. A
third, disabled configuration slot can be used for deliberate physical-arm tests.

> [!CAUTION]
> This is alpha software that can send commands to industrial robots. Validate
> workflows in URSim, keep physical robots disabled by default, and follow the
> manufacturer's safety procedures.

## Highlights

- Fleet overview and per-robot operator workspace
- Dashboard power, brake release, load, play, pause, stop, and move-home actions
- RTDE status monitoring with Dashboard fallback
- Local library and remote robot filesystem browsers with rename/move/copy/delete
- Whole-folder `.urp` bundle deployment with optional assignment and validation
- Explicit ready-for-play state based on the actual Dashboard response
- Direct `.script` execution as a separate workflow
- Read-only `.urp` analysis and conservative parameter editing
- More than 220 automated tests across services, adapters, CLI, and GUI

## Architecture

```text
FastAPI/Jinja GUI + CLI
          |
   service layer
    /     |      \
Dashboard RTDE  SSH/SFTP     direct script socket
    |      |      |                  |
         URSim or physical UR controller
```

Runtime control, robot filesystem operations, and direct script execution are
intentionally separate. A successful file upload does not imply successful
Dashboard load, and a successful load does not imply that PolyScope can play the
program.

## Windows quick start

### 1. Install and configure

From PowerShell in the repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item config\robots.example.yaml config\robots.yaml
```

`config/robots.yaml` is intentionally ignored by Git so real IP addresses and
credentials are not published. The example maps `robot1` and `robot2` to the two
local simulators and leaves the optional physical `robot3` disabled. The `easybot`
password in the example and Docker image is for local URSim only; never reuse it on
a physical controller.

### 2. Start URSim

Start Docker Desktop and wait for its Linux engine. On the first run, or after an
image change:

```powershell
.\scripts\start-ursim.ps1 -Rebuild
```

For later runs:

```powershell
.\scripts\start-ursim.ps1
```

Ordinary starts reuse existing containers and preserve their robot-side files. The
`-Rebuild` option force-recreates the containers and may replace container-local
state, so keep canonical programs in the local Library.

| Robot | PolyScope | Dashboard | Script | RTDE | SSH |
|---|---|---:|---:|---:|---:|
| robot1 | <http://127.0.0.1:6080/vnc.html> | 29991 | 30022 | 30024 | 2222 |
| robot2 | <http://127.0.0.1:6081/vnc.html> | 29992 | 30122 | 30124 | 2223 |

### 3. Start the application

```powershell
uam-gui
```

Wait for `Uvicorn running on http://127.0.0.1:8000`, then open
<http://127.0.0.1:8000/>. Keep that terminal open. `ERR_CONNECTION_REFUSED` means
the server is not running; WinError 10048 means another process already owns port
8000.

Health check:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

## Demonstration workflows

For a dependency-free demo, add `programs/simulation_demo/ursim_no_gripper_demo.script`
to the local library and use the direct script workflow. It does not require a
gripper URCap. Direct scripts sent through the secondary socket should contain one
top-level `def ... end` program and should not call that function again after `end`.
Direct script execution bypasses Dashboard load/readiness checks and can command
motion immediately; treat it as a dangerous, separate operator action.

For a PolyScope bundle:

1. Import a folder containing one `.urp` and its companion files.
2. Open Transfer, choose the bundle and robot destination.
3. Deploy with assignment and load validation enabled.
4. Continue to Robot Workspace and Play only when validation reports ready.

Programs containing Robotiq nodes require the compatible official Robotiq URCap.
The included TCP mock does not provide PolyScope nodes; `Missing: Gripper` therefore
prevents Play. See [URSim gripper limitations](docs/ursim_gripper_limitations.md).

## Tests

```powershell
python -m pytest -q
```

GitHub Actions runs the suite on Python 3.10 and 3.12 for every push and pull
request.

## Useful CLI commands

```text
uam robots list
uam robot status robot1
uam robot power-on robot1
uam robot brake-release robot1
uam robot load robot1
uam robot play robot1
uam robot stop robot1

uam robot files list robot1 /programs
uam library list
uam library inspect <library-path>
uam robot compatibility robot1 <library-path>
```

## Program library

The local library is `storage/library/` and is intentionally untracked. Its real
filesystem is the source of truth. A bundle is a normal folder containing one
primary `.urp` and optional `.installation`, `.variables`, `.script`, and `.txt`
companions. Deployment preserves that structure.

Dashboard-visible paths and SSH filesystem paths can differ between URSim and
PolyScope versions. The application derives the load argument centrally, preserves
the raw Dashboard response, and exposes the resulting readiness state.

## Home program configuration

The current Move Home action uses an existing robot-side `.urp` configured per robot:

```yaml
home_program: /programs/go_home.urp
```

The file must already exist on that robot and may require operator-side Automove
confirmation. Capturing joint positions and generating a controlled MoveJ home action
is a proposed future design; it is not implemented yet.

## Project status and limitations

- The backend, GUI, simulator workflow, and automated tests are implemented.
- URSim behavior has been manually exercised with the custom SSH image.
- In the two-container URSim profile, RTDE monitoring falls back to Dashboard because
  the installed receive API does not accept the forwarded custom ports.
- Dashboard response classification is necessarily heuristic across versions.
- Programs with third-party URCaps require legally obtained compatible bundles.
- Physical-arm validation remains environment-specific and must be performed with
  appropriate safety controls.
- The web UI has no authentication or CSRF protection. It is a trusted-local-operator
  interface bound to `127.0.0.1` by default, not an internet-facing service. Do not
  publish it through a proxy or bind it to an untrusted network.
- SFTP operations are restricted to the configured controller program roots. Localhost
  URSim accepts ephemeral SSH host keys; non-local controllers must have a trusted host
  key in the operator account's known-hosts store.
- Automated checks use fakes and do not validate robot cell risk assessment, safety I/O,
  payload/TCP setup, reachability, protective equipment, or manufacturer procedures.

See [Security](SECURITY.md), [Contributing](CONTRIBUTING.md), and the active notes
under `docs/` for more detail.

## License

Licensed under the [MIT License](LICENSE).
