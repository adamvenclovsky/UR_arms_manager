# GUI Phase Plan

This roadmap defines the disciplined 11-phase GUI delivery for `UR_arms_manager`.

The 11-phase GUI plan remains the long-term GUI roadmap.
Actual implementation may currently proceed through a mixed backend + GUI sprint plan.
The active short-term sprint plan is in `docs/sprint_plan_rtde_gui.md`.

## Phase 0 - Design prep and UI contracts
Goal:
- establish GUI contracts before implementation

Scope:
- documentation only
- no FastAPI routes, templates, JS, or CSS

Expected output:
- `docs/gui_phase_plan.md`
- `docs/gui_ui_contracts.md`
- `docs/gui_operator_workflows.md`
- README pointer to GUI plan docs

## Phase 1 - GUI foundation
Goal:
- stand up a minimal server-rendered GUI shell

Scope:
- FastAPI app entry and base layout wiring
- no robot actions yet

Expected output:
- runnable GUI app
- base layout and navigation frame
- health/readiness check endpoint

## Phase 2 - Robot overview dashboard
Goal:
- provide one-page overview of configured robots

Scope:
- static robot inventory from backend registry
- assigned program visibility

Expected output:
- dashboard screen with robot cards/table
- clear enabled/disabled indicators

## Phase 3 - Live robot status
Goal:
- expose near-real-time robot state for operators

Scope:
- polling-based status refresh
- connected/robot mode/safety/program-running visibility

Expected output:
- live status widgets on dashboard
- robust disconnected/error rendering

## Phase 4 - Robot actions
Goal:
- enable safe runtime control actions

Scope:
- power-on, brake-release, power-off
- load, play, stop
- action guards and confirmations where needed

Expected output:
- action controls per robot
- clear success/error feedback banners

## Phase 5 - Library browser
Goal:
- let operators browse local program library safely

Scope:
- list, inspect, remove library items
- clear `.urp` vs `.script` distinctions

Expected output:
- library list screen
- detail panel with metadata and origin info

## Phase 6 - Upload and import flows
Goal:
- ingest programs into library from operator workflows

Scope:
- local file upload/add flow
- import-remote from robot over SSH/SFTP

Expected output:
- upload/import forms
- validation and result feedback

## Phase 7 - Deploy and assignment flows
Goal:
- prepare robot execution targets from GUI

Scope:
- deploy to robot
- assign-remote
- assign-library
- assign-script

Expected output:
- assignment/deploy actions tied to robot + program
- explicit workflow labeling (dashboard/SSH/script)

## Phase 8 - Script workflow and quick operator actions
Goal:
- make direct `.script` operation fast and explicit

Scope:
- assign-script and run-script operator path
- quick actions for frequent script operations

Expected output:
- dedicated script execution flow
- reduced clicks for common script run sequence

## Phase 9 - URP detail, compatibility, safe params
Goal:
- support informed `.urp` decisions without unsafe editing

Scope:
- `.urp` metadata view
- compatibility advisory view
- whitelist-based safe parameter edits

Expected output:
- URP detail screen with compatibility signals
- safe parameter editor with guarded writes

## Phase 10 - UX hardening and visual consistency
Goal:
- increase operator trust, clarity, and misuse resistance

Scope:
- consistent component styling and labels
- better empty/error/loading/success messaging
- confirmation and disabled-state refinements

Expected output:
- visually coherent GUI
- reduced ambiguous or risky interactions

## Phase 11 - Final operator workflow validation
Goal:
- validate end-to-end operator readiness

Scope:
- execute key real workflows against URSim
- fix final usability blockers only

Expected output:
- validated first GUI release candidate
- concise operator runbook and acceptance checklist
