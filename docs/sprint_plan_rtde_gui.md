# Mixed Sprint Plan: GUI + Monitoring + RTDE

This document defines the active short-term implementation plan for the next mixed backend + GUI sprint.

The existing 11-phase GUI plan remains the long-term GUI roadmap.
This sprint plan is narrower and is intended to guide the next practical implementation steps across GUI work, backend monitoring improvements, and later RTDE adoption.

## Phase A - GUI robot actions
Goal:
- add GUI actions for:
  - power on
  - brake release
  - power off
  - load
  - play
  - stop

Scope:
- extend the existing robot overview/action area
- reuse existing backend action services
- add clear success/error feedback and safe disabled states
- no RTDE work yet

Expected output:
- GUI action controls for basic dashboard/runtime operations
- clear operator feedback for each action

## Phase B - RTDE research-to-code spike
Goal:
- add a small isolated RTDE proof of concept
- verify connection and basic status reads
- do not yet wire it deeply into the full GUI

Scope:
- isolated RTDE adapter/spike code
- verify connection behavior against URSim or supported targets
- basic read path only
- no broad architecture changes yet

Expected output:
- minimal RTDE proof of concept
- documented findings about connectivity, useful fields, and practical limits

## Phase C - RTDE monitoring integration
Goal:
- integrate RTDE as an optional monitoring backend
- keep Dashboard status as fallback
- improve live robot status with richer data where available

Scope:
- optional RTDE-backed monitoring path
- preserve current dashboard-based status fallback
- improve status payloads without breaking existing flows

Expected output:
- optional RTDE monitoring integration
- richer live status where RTDE is available
- dashboard fallback maintained

## Phase D - GUI library browser
Goal:
- GUI list/inspect/remove for library items
- show item type and origin

Scope:
- library browse and inspect screens
- remove action with clear confirmation
- distinguish `.urp` and `.script`

Expected output:
- library browser page
- item detail view with type/origin visibility
- remove flow with feedback

## Phase E - GUI upload/import flows
Goal:
- upload local file to library from GUI
- import remote file from robot to library from GUI

Scope:
- local upload/add flow
- remote import flow using existing backend behavior
- validation and user feedback only

Expected output:
- GUI upload form
- GUI remote import flow
- clear success/error states

## Phase F - GUI deploy and assignment flows
Goal:
- GUI flows for:
  - assign-remote
  - assign-library
  - assign-script
  - deploy

Scope:
- explicit workflow separation between dashboard paths, SSH/SFTP paths, and script assignment
- reuse existing backend assignment/deploy operations
- no script quick actions yet

Expected output:
- deploy flow
- assignment flows for remote, library, and script targets
- clear workflow labeling in the GUI

## Phase G - GUI script workflow
Goal:
- first-class `.script` workflow in GUI
- assign-script and run-script
- quick operator actions

Scope:
- `.script`-specific operator flow
- direct run path using existing script execution backend
- quick-action UX for common script tasks

Expected output:
- dedicated `.script` workflow in GUI
- assign-script and run-script entry points
- reduced-friction operator flow for direct scripts

## Phase H - GUI URP detail + compatibility + safe params
Goal:
- GUI detail for `.urp`
- parsed metadata
- compatibility result
- safe whitelisted param editing

Scope:
- `.urp` detail screen
- compatibility advisory rendering
- safe param editing limited to current whitelist approach
- no generic URP editing

Expected output:
- GUI `.urp` detail page
- compatibility view
- safe whitelisted parameter editing flow
