# URSim runtime notes

## Tested setup
- custom Docker image based on `universalrobots/ursim_e-series`
- added `openssh-server`
- SSH started manually via docker exec

## Port mapping example
- robot1
- robot2

## Web GUI URLs
- 6080
- 6081

## Dashboard ports
- 29991
- 29992

## Script ports
- 30022
- 30122

## SSH ports
- 2222
- 2223

## Observed filesystem paths
- `/ursim/programs.UR5/programs/<file>.urp`

## Observed dashboard load behavior
- works with `programs/<file>.urp`
- not reliable with `<file>.urp` alone

## Observed validated flows
- status
- power-on / brake-release / power-off
- SSH/SFTP list/exists/pull
- import-remote
- dashboard load/play/stop with correct path form