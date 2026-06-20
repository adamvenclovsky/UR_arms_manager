# URSim and Robotiq gripper programs

The repository's mock Robotiq service and the Robotiq PolyScope URCap solve
different problems:

- `mock_robotiq_gripper.py` emulates the gripper's TCP service on port 63353.
- The Robotiq URCap supplies PolyScope program nodes such as `Gripper`.

The mock service cannot make a missing PolyScope node valid. If a loaded program
shows `Missing: Gripper`, install the compatible official Robotiq URCap in URSim,
then restart/recreate the simulator and reopen the program. This repository intentionally
does not redistribute that third-party bundle.

Place a legally obtained URCap in `ursim-urcaps/` as a `.jar` file. The directory
is mounted at `/urcaps` by Docker Compose. Then run:

```powershell
.\scripts\start-ursim.ps1
```

If the program was created with a different URCap version, PolyScope may still
show missing nodes. Use a matching version or create a simulator-only program that
does not contain gripper nodes.

Dashboard `load` success only confirms that PolyScope loaded the project. It does
not guarantee that the program is executable. `play` can still be rejected because
of missing URCaps, unresolved installation data, safety state, required Automove
confirmation, or disabled Remote Control mode.

For a dependency-free demonstration, use the example `.script` programs under
`programs/` through the direct script workflow.
