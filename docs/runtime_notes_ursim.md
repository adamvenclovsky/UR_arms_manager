# URSim runtime notes

## Local profile

The project uses two containers built from `universalrobots/ursim_e-series` with
OpenSSH and a TCP-level mock Robotiq service.

| Service | robot1 | robot2 |
|---|---:|---:|
| PolyScope/noVNC | 6080 | 6081 |
| Dashboard | 29991 | 29992 |
| Script socket | 30022 | 30122 |
| RTDE forwarding | 30024 | 30124 |
| SSH/SFTP | 2222 | 2223 |

Start or resume the existing containers with:

```powershell
.\scripts\start-ursim.ps1
```

Use `-Rebuild` after changing the custom image. Ordinary starts reuse containers so
robot-side files survive. A rebuild/forced recreation can replace container-local
state; keep canonical programs in the local Library.

## Monitoring

The installed `ur-rtde` receive API accepts a host but not a custom TCP port. Because
the two simulators expose forwarded host ports, monitoring falls back to Dashboard in
this profile. Physical robots using standard port 30004 can use RTDE directly.

## Paths

Observed SSH paths use `/ursim/programs.UR5/...`, while Dashboard expects paths
relative to its program root. The application centralizes this conversion:

- `/ursim/programs.UR5/jobs/main.urp` → `jobs/main.urp`
- `/programs/main.urp` → `programs/main.urp`

Dashboard Load can take several seconds while PolyScope parses a program and its
installation; the Dashboard client therefore uses a longer timeout for Load than for
routine status commands.

## Runtime limitations

- Load success does not guarantee Play success.
- Motion programs may require operator-side start-position/Automove confirmation.
- URSim can report `remoteControl=false` even while some Dashboard actions work.
- A bundle installation created for another robot model can be rejected by PolyScope.
- The TCP mock does not provide missing PolyScope URCap program nodes.
