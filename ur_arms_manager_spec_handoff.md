# Product design principles (historical handoff)

This file records the principles used during implementation. For current setup and
supported behavior, use `README.md` and the documents under `docs/`.

## Product model (active)

- Local Library is a real local filesystem.
- Robot storage is a real remote filesystem over SSH/SFTP.
- Operators should see only files/folders that physically exist.
- UR program bundles are first-class where applicable.
- Dashboard runtime (`load/play/stop`) is separate from direct `.script` execution.
- Runtime/load readiness must be shown truthfully, including raw load-response context.

## Bundle model

- A bundle is a folder in local Library.
- Bundle primary runtime candidate is one deterministic `.urp` when present.
- `.installation` and `.variables` presence are operationally important and should be visible.
- Bundle deploy should preserve files/folder structure to robot storage.

## Runtime truth model

- Keep assigned runtime target simple (single assigned remote `.urp` path).
- Derive dashboard `load` argument in one helper near load time.
- If load/play cannot proceed, show clear reason instead of implied success.
- Environment-specific assumptions must be explicit and non-universal.

## Workflow boundaries (must remain explicit)

- Library filesystem management (local)
- Robot filesystem management (remote SSH/SFTP)
- Assignment/runtime preparation
- Dashboard runtime controls
- Direct `.script` execution

## Implementation constraints

- No manifest-centric source-of-truth reintroduction.
- No heavy frontend stack required for GUI.
- Prefer small, safe, testable diffs over broad rewrites.
