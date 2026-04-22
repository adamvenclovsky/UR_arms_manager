# Filesystem-First Redesign Plan

This document defines the next storage and GUI redesign track for `UR_arms_manager`.

The project currently has a functional backend and GUI.
The next product direction is intentionally shifting away from manifest-based library items and toward a filesystem-first model.

In the target model:
- the local Library is a real filesystem on the central computer
- each robot storage is a real filesystem over SSH/SFTP
- the GUI shows only files and folders that physically exist
- manifest metadata is no longer the primary source of truth

This plan is documentation-only.
It does not authorize implementation work by itself.

## Phase FS1 - Docs, contracts, migration strategy
Goal:
- rewrite project direction from manifest-based library items to filesystem-first storage
- define the new storage model and migration direction

Scope:
- documentation, contracts, and migration notes only
- clarify which old assumptions are being retired
- define phased replacement strategy for manifest-driven tests and workflows

Expected output:
- filesystem-first storage contracts
- migration/testing notes for replacing manifest-based assumptions
- clear direction for backend and GUI implementation phases

## Phase FS2 - Filesystem-first backend for local library
Goal:
- make local library listing and operations work directly on real files and folders
- remove manifest-driven source-of-truth behavior

Scope:
- local library backend only
- list, inspect, create folder, move, copy, remove based on actual filesystem state
- manifest logic removed or isolated from runtime-critical paths

Expected output:
- local library backend operating directly on real files/folders
- no manifest-based identity as the primary runtime model
- clear error handling for real filesystem edge cases

## Phase FS3 - Library GUI redesign as real file manager
Goal:
- redesign `/library` into a real file manager over local library storage

Scope:
- local library GUI only
- folder navigation, file selection, and file-manager-style operations
- show only files/folders that physically exist

Expected output:
- `/library` behaves like a real local file manager
- clearer operator understanding of folders, files, and available actions
- no manifest-style internal item identity as the main UI model

## Phase FS4 - Robot storage backend and file-manager operations
Goal:
- make robot-side file operations behave like a real remote file manager

Scope:
- robot-side storage backend only
- browse, create folder, move, copy, remove, and related file operations as appropriate over SSH/SFTP
- preserve clear separation from dashboard runtime semantics

Expected output:
- robot storage backend centered on real remote filesystem behavior
- file-manager operations for robot storage with readable error handling
- better parity between local Library and robot storage concepts

## Phase FS5 - Robot workspace redesign around real robot storage
Goal:
- make each robot workspace show and act on actual robot-side files

Scope:
- robot workspace UX only
- real robot file tree, real robot-side selections, and runtime context
- no manifest-style library item assumptions

Expected output:
- robot workspaces centered on actual remote files/folders
- clearer operator flow from browse -> select -> runtime action
- reduced ambiguity between assignment state and physical robot storage

## Phase FS6 - Transfer flows between Library and robot storage
Goal:
- make library-to-robot and robot-to-library transfers explicit and file-based

Scope:
- transfer UX and backend behavior between the two filesystems
- import robot file to Library with automatic robot-name filename prefix
- send/copy flows based on real paths and files only

Expected output:
- explicit filesystem-to-filesystem transfer model
- robot-to-library imports that create names like `robot1_original_name.urp`
- operator-friendly transfer flows with clear path visibility

## Phase FS7 - Assignment/runtime simplification and legacy cleanup
Goal:
- simplify runtime flows so assignment/load are based on robot-side files only
- remove or isolate old manifest-style assumptions

Scope:
- runtime flow cleanup
- assignment/load behavior based on real robot storage paths
- legacy compatibility isolation or removal where appropriate

Expected output:
- runtime model based on actual robot-side files
- reduced legacy storage assumptions
- cleaner long-term backend and GUI behavior

## Migration and testing note
- existing manifest-based tests and assumptions will need phased replacement
- new tests should validate real filesystem behavior, not manifest metadata behavior
- migration should happen incrementally so existing user data and workflows can be transitioned safely
