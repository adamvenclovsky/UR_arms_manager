# Program Bundle Workflow (Filesystem-First)

This note defines the bundle workflow added in the current sprint.

## Why bundles

For real UR/PolyScope runtime, a `.urp` file is often not enough by itself.
Programs commonly depend on related files in the same folder, especially:
- `.installation`
- `.variables`
- optional `.script`
- optional `.txt`

Because of that, this project now treats a deployable UR program as a **folder bundle**, not just one file.

## Bundle model

- A bundle is a real directory under local library storage.
- Filesystem is the source of truth.
- Bundle metadata is derived by scanning files in that folder.

Bundle inspection returns:
- bundle name and folder path
- detected primary `.urp` (or none)
- grouped files by type
- presence flags for installation/variables/script/text
- readiness state and warnings

Primary `.urp` detection:
- exactly one `.urp` => primary runtime candidate
- zero `.urp` => invalid for dashboard runtime
- multiple `.urp` => ambiguous; warning, no silent guess

## Bundle import

- The GUI `/library` upload accepts multiple files.
- If one file is selected, behavior stays single-file upload.
- If multiple files are selected, system creates one new bundle folder and copies all selected files into it.
- Bundle folder name is sanitized and derived from the upload set (prefer single `.urp` stem when available).
- If primary `.urp` filename contains runtime-unsafe characters (spaces/quotes/semicolons/tabs), preview shows a rename plan and commit stores a runtime-safe copied filename by default.
- Source files on operator machine are not mutated; normalization applies only to copied files stored in local Library.
- New libraries start with an empty root; uploads/imports can target root directly (no pre-created `uploaded/` folder is required).
- Robot-to-library imports no longer require auto-created robot subfolders; imports can land in library root.

## Bundle deploy

- Deploy can now accept a selected library bundle folder.
- System uploads the whole folder tree to robot storage.
- Per-file deploy results are returned.
- The deployed primary `.urp` path is returned as runtime candidate.
- Optional GUI checkbox allows assigning that deployed primary `.urp` immediately as robot runtime target.

## Runtime/load validation hardening

- Dashboard load response parsing is hardened.
- Parser/rejection responses (for example `could not understand: 'load ...'`) are treated as failures, not success.
- Raw dashboard response is preserved in the raised error to keep manual validation trustworthy.
- Validation is blocked for known runtime-unsafe derived dashboard load arguments (for example names with spaces) and reports explicit `unsafe_runtime_path`.

## Current sprint boundary

Implemented:
- bundle import
- bundle inspection summary
- bundle deploy + primary runtime candidate
- optional post-deploy assignment
- truthful dashboard load success/failure handling

Still open for later phases:
- deeper runtime compatibility solving
- advanced dashboard path normalization strategies across all URSim variants
- optional "prepare runtime-safe copy" action for already imported legacy bundles
