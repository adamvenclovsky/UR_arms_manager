# Filesystem-first architecture

The redesign described by the original version of this document is implemented.

## Local library

- `storage/library/` is the local library root.
- Real files and directories are the source of truth.
- A new library starts empty; no manifest or predefined folder is required.
- The GUI supports browse, inspect, upload, create folder, rename, move, copy, and
  remove operations.
- `.urp` parsing and editable-parameter metadata are derived from the selected file.

## Robot storage

- Robot files are accessed over SSH/SFTP.
- The robot workspace supports browse, create folder, rename, move, file copy,
  remove, import to Library, and direct execution of selected `.script` files.
- Filesystem selection does not silently change Dashboard runtime assignment.
- Renaming an assigned remote file or a parent folder updates the stored assignment.

## Transfer and runtime boundaries

- Library-to-robot transfer copies real files or a complete directory tree.
- Robot-to-library import copies one selected file.
- A bundle is a folder with one deterministic primary `.urp` and optional companion
  `.installation`, `.variables`, `.script`, and `.txt` files.
- Deployment, assignment, Dashboard Load/Play, and direct script execution remain
  explicit separate operations.

## Legacy data

The older `storage/programs/` manifest layout is not used by current runtime paths.
Local legacy data may be migrated manually into `storage/library/`; it is intentionally
not committed to the public repository.
