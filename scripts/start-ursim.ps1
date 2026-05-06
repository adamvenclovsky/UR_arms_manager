param(
    [switch] $Rebuild
)

$ErrorActionPreference = "Stop"

$composeArgs = @("compose", "-f", "docker-compose.ursim.yml")
if ($Rebuild) {
    docker @composeArgs build
}

docker stop ursim1 ursim2 2>$null | Out-Null
docker rm ursim1 ursim2 2>$null | Out-Null

docker @composeArgs up -d

docker exec ursim1 sh -lc "ssh-keygen -A && mkdir -p /run/sshd && pkill sshd || true && /usr/sbin/sshd"
docker exec ursim2 sh -lc "ssh-keygen -A && mkdir -p /run/sshd && pkill sshd || true && /usr/sbin/sshd"
docker exec ursim1 sh -lc "/opt/uram/start_mock_robotiq.sh"
docker exec ursim2 sh -lc "/opt/uram/start_mock_robotiq.sh"

docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
