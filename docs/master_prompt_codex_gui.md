# Master prompt for Codex — GUI stage

You are implementing the GUI stage of the project `UR_arms_manager`.

## Project state
The backend and CLI core of `UR_arms_manager` already exist and are functional.

The system already supports:
- YAML robot configuration
- robot registry
- robot status via Dashboard
- dashboard runtime actions:
  - load
  - play
  - stop
- robot power control:
  - power-on
  - brake-release
  - power-off
- robot-side file access over SSH/SFTP
- local library:
  - add
  - list
  - inspect
  - remove
- library import from robot
- deploy from library to robot
- assign-remote
- assign-library
- assign-script
- direct `.script` execution with run-script
- read-only `.urp` metadata analysis
- compatibility advisory
- limited safe `.urp` parameter editing

## Important observed runtime notes
In the tested custom URSim Docker setup with SSH enabled:
- SSH/SFTP file paths looked like:
  `/ursim/programs.UR5/programs/<file>.urp`
- Dashboard `load` worked with:
  `programs/<file>.urp`
- Dashboard `load` did NOT reliably work with only:
  `<file>.urp`

The GUI must not hide the difference between:
- dashboard-visible program paths
- raw SSH filesystem paths
- direct `.script` execution workflow

## Goal of the GUI stage
Build a robust, operator-friendly GUI for non-terminal users.

The GUI should let the user:
- see which robots exist
- see whether they are connected
- see their live status
- see assigned programs
- control power/load/play/stop
- browse the program library
- upload/import programs
- assign and deploy programs
- run `.script` items
- inspect `.urp` metadata
- check compatibility
- edit only safe whitelisted `.urp` params

## GUI architecture rules
1. Keep the existing Python backend core as the source of truth.
2. Do not duplicate business logic in the GUI layer.
3. Prefer a lightweight stack.
4. Prefer server-rendered pages with small JS enhancements over a heavy SPA.
5. Every GUI screen must handle:
   - loading state
   - empty state
   - error state
   - success feedback
6. Reuse UI components instead of inventing page-specific one-offs.
7. Keep the GUI operator-friendly and hard to misuse.
8. Do not add ROS 2, Electron, Qt, or heavy frontend infrastructure unless explicitly requested.
9. Do not perform large unrelated refactors.

## Recommended GUI stack
- FastAPI
- Jinja2 templates
- HTMX
- small amounts of vanilla JavaScript
- lightweight CSS

## Do not default to
- React SPA
- large frontend build systems
- websockets in the first iterations
- background workers unless explicitly needed later

## Component strategy
Prefer a small reusable UI component set:
- app layout shell
- top navigation
- robot card
- status badge
- action button row
- result banner / toast
- file/program table
- detail panel
- confirmation dialog
- compatibility badge
- polling status indicator

## Quality bar
The GUI should feel safe and understandable for non-programmer operators.
Buttons must not be misleading.
Potentially dangerous or state-sensitive actions should be clearly labeled and, where appropriate, disabled or confirmed.

## Workflow rules for every GUI task
1. Respect the exact current phase scope.
2. Make the smallest coherent change that satisfies the phase.
3. Reuse existing backend services wherever possible.
4. Add or update tests where appropriate.
5. Keep code readable and explicit.
6. Do not silently expand scope.

## Output rules
For every GUI phase implementation:
1. Briefly explain what you are changing.
2. List the files you are creating or modifying.
3. Show the full content of every new or changed file.
4. End with:
   - what is completed
   - how to run it
   - how to manually test it
   - what is intentionally not included yet

## GUI phase discipline
The GUI implementation follows an 11-phase plan.
Do not jump ahead.
Do not implement future phases early.
Do not add features outside the requested phase.

## GUI phase plan
Phase 0 - Design prep and UI contracts
Phase 1 - GUI foundation
Phase 2 - Robot overview dashboard
Phase 3 - Live robot status
Phase 4 - Robot actions
Phase 5 - Library browser
Phase 6 - Upload and import flows
Phase 7 - Deploy and assignment flows
Phase 8 - Script workflow and quick operator actions
Phase 9 - URP detail, compatibility, safe params
Phase 10 - UX hardening and visual consistency
Phase 11 - Final operator workflow validation