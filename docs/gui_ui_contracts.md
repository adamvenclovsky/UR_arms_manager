# GUI UI Contracts

Purpose: define implementation contracts for the operator GUI before screen coding begins.

## 1. Main screens

Workspace direction note:
- the existing GUI remains functional, but the next GUI redesign track moves toward a workspace-style model
- future GUI phases should treat System, Library, and each Robot view as operator workspaces rather than one generic dashboard plus utility pages
- the next storage direction also moves toward a filesystem-first model for both local Library and robot storage

### 1.1 Dashboard
- Shows configured robots and their current assigned target.
- Shows live status summary per robot.
- Entry point for power/runtime actions.

Primary data:
- robot identity/config (`name`, `host`, ports, `enabled`)
- assignment summary (`assigned_program`)
- live status (`connected`, `robotmode`, `safety_status`, `program_running`)

### 1.2 Robot detail/actions
- Focused control area for one robot.
- Exposes guarded actions: power-on, brake-release, power-off, load, play, stop.
- Shows recent action result and current state context.

Primary data:
- robot config + live status
- action capability flags (enabled/disabled reasons)

Workspace direction:
- evolve this into robot-specific workspace pages
- each robot workspace should combine status, actions, assigned program visibility, and robot-side file context
- robot-side file context should be based on actual remote files/folders, not manifest-style library identity

### 1.3 Library browser
- Lists local library items.
- Supports inspect/remove and type distinction (`.urp`, `.script`).
- Links to assignment/deploy/script workflows.

Primary data:
- library manifest list
- selected item detail (metadata, origin, type)

Workspace direction:
- evolve this into a file-manager-style Library workspace
- make file origin, storage state, assignment relationships, and transfer actions easier to inspect
- local Library should be treated as a real local filesystem with files/folders as the source of truth

### 1.4 System / diagnostics
- Shows configuration sanity and environment diagnostics.
- Highlights missing or suspicious robot config before operator action begins.

Primary data:
- robot config summary
- missing/invalid field checks
- local runtime/environment sanity hints
### 1.5 Import/upload screen
- Handles adding local file to library.
- Handles importing remote robot file into library.

Primary data:
- robot selection (for remote import)
- remote path input
- local file input
- operation result payload
### 1.6 Deploy/assignment screen
- Handles robot-program preparation actions.
- Exposes assign-remote, assign-library, assign-script, deploy.
- Clearly labels which runtime model each action belongs to.

Primary data:
- selected robot
- selected library item or path
- assignment result
### 1.7 Program detail (URP/script)
- For `.urp`: metadata, compatibility advisory, safe parameter editor.
- For `.script`: execution-focused information and run entry points.

Primary data:
- program detail payload
- compatibility payload
- safe editable params payload

### 1.8 Robot file manager
- Shows files currently stored on one robot.
- Supports robot-side browse/inspect context for SSH/SFTP workflows.

Primary data:
- selected robot
- remote file list
- remote path context

## 1.9 Transfer flow direction
- Transfer UX should become explicit between:
  - Library workspace
  - robot file manager
  - robot assignment/runtime context
- Transfer flows should operate between two real filesystems:
  - local Library filesystem
  - robot filesystem over SSH/SFTP
- The GUI should make it obvious whether an action is:
  - local library storage
  - robot file storage
  - assignment only
  - direct `.script` execution
- The GUI should avoid manifest-based source-of-truth assumptions when presenting files and folders.

## 2. Reusable UI components
- `AppShell`: layout, top nav, global feedback zone.
- `RobotCard`: robot identity, assignment summary, quick status/action entry.
- `StatusBadge`: connected/mode/safety/program-running indicators.
- `ActionRow`: grouped action buttons with disabled reasons.
- `ResultBanner`: success/error/warning/info feedback.
- `ProgramTable`: reusable list for library and robot file listings.
- `DetailPanel`: selected item detail and metadata.
- `ConfirmDialog`: explicit confirmation for risky actions.
- `CompatibilityBadge`: pass/warn/fail advisory indicator.
- `PollingIndicator`: last refresh timestamp and polling health.

## 3. Workflow boundaries (must stay explicit)

### 3.1 Dashboard workflow (`.urp` run control)
Purpose:
- run robot-side dashboard operations on assigned robot-visible path.

Actions:
- assign-remote or assign-library (to establish robot-visible `.urp` path)
- load -> play -> stop

Contract rules:
- GUI must show assigned path exactly as controller expects.
- GUI must not pretend SSH filesystem path equals dashboard load path.

### 3.2 SSH/SFTP file workflow (file transport/inspection)
Purpose:
- browse/existence-check/pull/import/deploy robot files.

Actions:
- files list/exists/pull
- import-remote
- deploy

Contract rules:
- GUI must show full remote filesystem path in this workflow.
- GUI must not auto-relabel SSH path as dashboard path without explicit mapping.

### 3.3 Direct `.script` workflow (script socket execution)
Purpose:
- run library `.script` directly via script socket, independent of dashboard load/play.

Actions:
- assign-script
- run-script

Contract rules:
- GUI must label this as direct script execution.
- GUI must not route `.script` items through dashboard load/play semantics.

## 4. Required state model for every screen/action
All screen loads and mutations must support these states explicitly:
- `loading`: data fetch/action in progress; controls guarded from duplicate submission.
- `empty`: valid no-data state with operator guidance.
- `error`: failure state with actionable message and retry path.
- `success`: clear confirmation after mutation or completed fetch.

Minimum state-handling expectations:
- each async operation has a visible progress indicator
- each failed operation returns user-facing reason (or safe fallback message)
- each successful mutation produces a visible success banner/toast

## 5. GUI data/API expectations (high-level)

### 5.1 Source-of-truth rule
- GUI layer consumes backend services as-is.
- No business-logic duplication in templates/JS.

### 5.2 Read contracts
Needed backend read capabilities for GUI:
- list robots + static config fields
- fetch robot live status
- list library items
- inspect library item detail/metadata
- retrieve compatibility advisory and safe param candidates
- list robot-side files (SSH/SFTP)

### 5.3 Write contracts
Needed backend write/action capabilities for GUI:
- power/runtime actions (power-on, brake-release, power-off, load, play, stop)
- assignment actions (assign-remote, assign-library, assign-script)
- run-script action
- library actions (add, remove, import-remote)
- deploy action
- safe `.urp` parameter update action

### 5.4 Response behavior expectations
- action responses should include: operation name, target robot/program, outcome status, message.
- validation failures should return field-specific errors where possible.
- status endpoints should tolerate unreachable robots and return structured disconnected/error state.

## 6. Non-goals for this phase
- no FastAPI route implementation
- no template implementation
- no frontend JS/CSS implementation
- no backend refactor
