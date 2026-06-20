# Runtime Validation for Deployed Program Bundles

This note describes the runtime-validation layer added on top of bundle deploy/import.

## Scope

This is a focused validation step for dashboard `.urp` runtime flow:
- bundle is deployed to robot storage
- a main `.urp` path is assigned
- dashboard `load` is attempted and classified truthfully

It does not redesign runtime architecture or `.script` workflow.

## Central load-argument derivation

Assigned runtime path remains a single canonical remote path (for example `/programs/demo.urp`).
Dashboard `load` argument is derived in one helper:
- `/programs/<file>.urp` -> `programs/<file>.urp`
- current URSim profile roots are mapped to dashboard-relative paths:
  - `/ursim/programs.UR5/<path>.urp` -> `<path>.urp`
  - `/ursim/programs/<path>.urp` -> `<path>.urp`
- relative dashboard-style paths are preserved
- unsupported absolute Linux paths are rejected (not passed through to dashboard `load`)

Helper location:
- `ur_arms_manager.services.runtime_validation.derive_dashboard_load_argument`

## Structured load validation result

`RobotManager.validate_assigned_runtime_load()` now returns:
- robot name
- assigned runtime path
- derived dashboard load argument
- raw dashboard response
- outcome classification
- notes
- `ready_for_play` flag

Outcomes:
- `success`
- `unsafe_runtime_path`
- `parser_error`
- `file_not_found`
- `load_error`
- `path_strategy_unknown`
- `timeout`
- `installation_or_safety_block`
- `wrong_mode_or_remote_control_issue`
- `unknown_failure`

Classification is response-based and heuristic. Inferred causes are treated as probable, not guaranteed.

## Runtime readiness snapshot

A lightweight readiness snapshot distinguishes practical states:
- deployed only
- assigned
- load attempted
- load succeeded
- load failed
- ready for play / not ready for play

This snapshot is used in robot workspace API/UI context to keep operator messaging truthful.

## Play hardening

GUI action API blocks `play` if the latest recorded load validation for that robot is not `success`.
The response keeps explicit outcome and last load context.

The most recent validation is process-local GUI state and is reset when `uam-gui`
restarts. Operators should validate again after a restart or assignment change.

## What is confirmed now

- load path derivation is centralized and test-covered
- unsupported absolute runtime paths are surfaced as `path_strategy_unknown`
- runtime-unsafe derived dashboard load arguments are blocked as `unsafe_runtime_path` before dashboard call
- parser/file-not-found/error responses are not treated as success
- structured load validation is exposed to GUI/API layer
- readiness notes distinguish assigned vs deployed-only mismatch
- GUI surfaces warning when runtime filename contains spaces/unsafe characters
- Dashboard Load uses a dedicated 15-second timeout; routine status commands retain
  the shorter timeout

## Environment-specific / still open

- exact dashboard response wording differs across URSim images and PolyScope versions
- installation/safety/mode detection is currently heuristic based on response text
- physical-arm validation remains a later step
- successful Load cannot prove that PolyScope will accept Play or Automove
