# GUI Operator Workflows

This document defines operator-facing end-to-end workflows the GUI must support clearly.

## Workflow 1: Power on robot and release brakes
Goal: move robot from powered-off state to operable state.

Steps:
1. Open Dashboard and select target robot.
2. Verify robot connectivity/status indicator.
3. Run `Power On`.
4. Confirm success feedback and mode transition away from `POWER_OFF`.
5. Run `Brake Release`.
6. Confirm success feedback and expected operable mode.

Operator checks:
- action buttons show disabled reason if robot unavailable
- each step shows explicit success/error message

## Workflow 2: Assign remote `.urp`, load, play, stop
Goal: execute robot-side `.urp` through dashboard runtime flow.

Steps:
1. Open Deploy/Assignment screen.
2. Select robot.
3. Choose `Assign Remote`.
4. Enter controller-visible dashboard path (example pattern: `programs/<file>.urp`).
5. Save assignment and confirm assigned path shown on robot summary.
6. From Robot Actions, run `Load`.
7. After successful load, run `Play`.
8. Run `Stop` when operation should halt.

Operator checks:
- GUI distinguishes dashboard path from SSH filesystem path
- `Load` failure surfaces exact returned reason

## Workflow 3: Import `.urp` from robot into library
Goal: capture an existing robot file into local managed library.

Steps:
1. Open Import/Upload screen.
2. Select target robot.
3. Choose `Import Remote`.
4. Enter full remote SSH path to `.urp`.
5. Submit import.
6. Verify success message with created library item id.
7. Open Library Browser and confirm new item appears.

Operator checks:
- remote path field guidance uses SSH/SFTP semantics
- duplicate/error outcomes are clearly explained

## Workflow 4: Deploy library item to robot
Goal: copy a managed library program onto robot storage.

Steps:
1. Open Library Browser and select program item.
2. Choose `Deploy`.
3. Select target robot and remote destination directory.
4. Confirm deploy action.
5. Verify success feedback includes remote target path.
6. (Optional) run remote file existence check via GUI file view.

Operator checks:
- deploy action confirms robot + item + destination before execution
- errors include connection/path permission context where available

## Workflow 5: Assign and run a `.script`
Goal: execute direct script workflow without dashboard load/play.

Steps:
1. Open Library Browser and select a `.script` item.
2. Choose `Assign Script` for target robot.
3. Confirm assignment summary shows script assignment marker.
4. Run `Run Script` action.
5. Confirm action result message.

Operator checks:
- GUI labels this as direct script socket execution
- `.script` path does not appear in dashboard load controls as if it were `.urp`

## Workflow 6: Inspect compatibility and safe `.urp` params
Goal: verify program suitability and edit only approved parameters.

Steps:
1. Open Library Browser and select `.urp` item.
2. Open program detail view.
3. Review metadata summary and compatibility advisory for selected robot.
4. Open safe parameter section.
5. Edit only available whitelisted parameters.
6. Submit update and confirm success result.
7. Re-open inspect view to verify persisted values.

Operator checks:
- compatibility outcome is visually explicit (ok/warn/fail)
- non-whitelisted fields are not editable
- invalid values return actionable validation messages

## Workflow 7: Inspect system/config sanity
Goal: detect configuration problems before runtime operations begin.

Steps:
1. Open System page.
2. Review configured robots and exposed host/port mapping summary.
3. Check for disabled robots, missing config values, or suspicious port mappings.
4. Resolve obvious config issues before using robot workspaces.

Operator checks:
- config problems are visible before action attempts fail
- mismatched local URSim/Docker mappings are explained plainly

## Workflow 8: Inspect one robot workspace
Goal: work on one robot with less ambiguity than a shared overview page.

Steps:
1. Open the selected robot workspace.
2. Review robot identity, live state, assigned program, and action area.
3. Review any robot-side file context shown in the workspace.
4. Use only the actions relevant to that robot.

Operator checks:
- operator can focus on one robot without losing assignment context
- robot-specific status and file context are grouped clearly

## Workflow 9: Browse library files
Goal: inspect local managed files as a workspace, not only as a flat list.

Steps:
1. Open Library workspace.
2. Browse real local files and folders by path, type, and storage location.
3. Select one file to inspect detail and available actions.
4. Confirm whether the file is suitable for deploy, assign, or direct script workflow.

Operator checks:
- only files/folders that physically exist are shown
- `.urp` and `.script` usage differences remain obvious

## Workflow 10: Browse robot files
Goal: inspect what is currently stored on one robot.

Steps:
1. Open the robot file manager area for a selected robot.
2. Browse remote files and directories.
3. Verify the exact robot-side path before load, deploy, or import decisions.

Operator checks:
- remote filesystem paths are shown as SSH/SFTP paths
- robot file browsing is not confused with dashboard assignment paths

## Workflow 11: Send library file to robot
Goal: move one managed local file onto robot storage clearly.

Steps:
1. Select a file in Library workspace.
2. Choose send/deploy to a target robot.
3. Confirm destination robot and remote directory/path.
4. Verify success feedback includes the remote target path.

Operator checks:
- transfer destination is explicit
- operator can distinguish deploy from assign

## Workflow 12: Import robot file into library
Goal: move one robot-side file into managed local library storage.

Steps:
1. Open a robot file view or transfer/import flow.
2. Select target robot and exact remote path.
3. Run import into Library.
4. Verify the imported file appears in Library with a robot-name-prefixed filename.

Operator checks:
- imported file is clearly visible as a real local file
- remote path and local library path are not conflated

## Workflow 13: Inspect assignment relationships
Goal: understand how library items, robot files, assignments, and runtime state relate.

Steps:
1. Open Library or a robot workspace.
2. Select a file or robot.
3. Review whether the file exists in local Library, on the robot, assigned on the robot side, or runtime-loaded.
4. Confirm the correct next action from that state.

Operator checks:
- operator can tell what exists where
- assigned path, remote file, and runtime-loaded program are not conflated

## Cross-workflow UX requirements
- Every flow supports `loading`, `empty`, `error`, and `success` states.
- Potentially risky actions (power-off, remove, deploy overwrite, param write) require confirmation.
- Robot unavailability must never produce ambiguous UI; show disconnected state and retry action.
- Success/error feedback must name robot and program affected.
- Workspace flows must keep local library storage, robot storage, assignment, and runtime state conceptually separate.
- Filesystem-first flows must use real local and remote paths as the operator-facing model.
