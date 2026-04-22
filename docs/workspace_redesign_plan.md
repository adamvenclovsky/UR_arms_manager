# Workspace Redesign Plan

This document defines the next GUI redesign track for `UR_arms_manager`.

The previous mixed backend + GUI sprint is complete.
The current GUI is functional, but the target UX is shifting to a workspace-style operator model.

This plan is documentation-only.
It does not authorize implementation work by itself.

## Phase R1 - System page and configuration sanity
Goal:
- replace the current placeholder-like System page with a real diagnostics/system page
- surface robot configuration sanity issues early
- help detect wrong ports, disabled robots, missing config values, and mismatched Docker mappings

Scope:
- system/diagnostics page only
- configuration summary and sanity checks
- no new robot control behavior
- no backend refactor

Expected output:
- real System page specification and implementation phase
- clear visibility of config issues before operator actions begin
- early operator guidance for broken local URSim mappings

## Phase R2 - Robot workspace pages
Goal:
- move from one generic robots page toward separate robot workspaces
- each robot should have its own clearer operational page/view

Scope:
- one workspace route/view per robot
- robot-specific live state, assigned program, actions, and related file context
- preserve current backend service boundaries

Expected output:
- dedicated robot workspace structure
- clearer operator context per robot
- less ambiguity than a single shared overview page

## Phase R3 - Library redesign as file manager
Goal:
- redesign Library into a file-manager-style workspace
- make files, file types, origin, assignments, and actions easier to understand

Scope:
- library listing and detail redesign only
- clearer item grouping, metadata visibility, and action placement
- keep existing backend library behavior as the source of truth

Expected output:
- file-manager-style Library page
- clearer visibility of `.urp`, `.script`, origin, and storage state
- more obvious operator actions tied to each item

## Phase R4 - Robot file manager
Goal:
- show the robot-side files more clearly
- allow browsing what is currently stored on a robot
- prepare the robot-side file manager UX

Scope:
- robot-side file listing and inspection UX
- SSH/SFTP file workflow visibility
- no broad remote file manipulation beyond current safe capabilities

Expected output:
- robot file manager view
- clearer visibility of remote paths and stored files per robot
- explicit separation from dashboard-visible assignment paths

## Phase R5 - Transfer flows between Library and robots
Goal:
- make Library -> Robot deploy/send flows clearer
- make Robot -> Library import flows clearer
- support operator-friendly movement of files between local library and robot storage

Scope:
- transfer-focused UX only
- library import and robot deploy flows presented as explicit send/import operations
- no backend architecture rewrite

Expected output:
- clearer transfer entry points
- less confusion between local library, robot storage, and assignment state
- practical operator send/import flow definitions

## Phase R6 - Assignment visibility and traceability
Goal:
- clearly show which files are assigned to which robots
- show relationships between library items, robot files, assigned programs, and runtime-loaded programs

Scope:
- assignment relationship visibility
- traceability between storage location, assignment target, and runtime usage
- no new runtime behavior

Expected output:
- assignment/traceability model in the GUI
- clearer operator understanding of what is assigned, where the file lives, and what the robot will load or run

## Phase R7 - UX cleanup and consistency
Goal:
- unify the final workspace UX
- reduce clutter
- improve operator clarity, defaults, warnings, and confirmations

Scope:
- cleanup and consistency pass across System, Library, robot workspaces, and transfer flows
- labels, defaults, warnings, and confirmation refinements
- no unrelated feature expansion

Expected output:
- coherent workspace-style GUI
- reduced operator ambiguity
- final consistency layer before deeper validation/testing phases
