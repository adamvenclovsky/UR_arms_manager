# Program bundle workflow

A deployable PolyScope program is often more than one `.urp` file. UR Arms Manager
treats a bundle as a real directory containing one primary `.urp` plus optional
`.installation`, `.variables`, `.script`, and `.txt` companions.

## Detection and readiness

- Exactly one `.urp`: deterministic primary runtime candidate.
- No `.urp`: ordinary folder, not Dashboard-deployable as a bundle.
- Multiple `.urp` files: ambiguous and blocked from bundle runtime deployment.
- Missing installation or variables companions produce warnings rather than a false
  guarantee of incompatibility.
- Unsafe primary filenames are reported and can be normalized through a
  non-destructive runtime-safe copy.

## Import

The Library upload supports one file or a staged multi-file bundle. Staging previews
the chosen folder name, file groups, primary `.urp`, warnings, and any filename
normalization before committing files to the library. Source files are never changed.

## Deploy and assignment

Transfer uploads the complete directory tree and reports per-file results. The
deployed primary `.urp` can optionally become the robot's assigned runtime target.
Assignment is stored as one canonical remote path and remains separate from upload.

The optional validation step calls Dashboard Load, preserves the raw response, and
classifies readiness. PolyScope may still reject Play after a successful Load because
of Remote Control mode, Automove confirmation, safety configuration, installation
compatibility, or missing URCaps.

## File management

Library and robot workspaces support explicit rename and move operations. Renaming a
robot path that is currently assigned also updates the assignment, including paths
inside a renamed parent directory.
