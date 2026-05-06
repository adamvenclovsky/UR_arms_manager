# URSim URCaps

Put URCap bundles for the simulator in this directory before starting Docker Compose.

The official Universal Robots Docker image loads URCaps from `/urcaps`. For bind-mounted
URCaps, the files in this folder should be `.jar` files. URCap files are Java bundles, so
if you receive `Robotiq_Grippers-<version>.urcap`, copy or rename it here as:

```text
Robotiq_Grippers-<version>.jar
```

Expected for `zaboj_fiala_program`:

```text
Robotiq_Grippers-3.19.1.111718.jar
```

After adding or replacing URCaps, recreate the containers and restart PolyScope.
