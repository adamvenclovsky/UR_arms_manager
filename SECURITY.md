# Security

This application can power and command industrial robots. Treat every configured
endpoint as safety-critical.

- Test new behavior in URSim before using a physical arm.
- Keep physical robots disabled in configuration until deliberately needed.
- Do not expose the web server, Dashboard, RTDE, script, or SSH ports to untrusted
  networks.
- Never commit real credentials or production robot configuration.
- Maintain physical emergency-stop access and follow the robot manufacturer's
  safety procedures.

Physical robots are disabled by default. Enabling one is an explicit local
configuration change. The service layer blocks Dashboard, script-socket, and SFTP
operations while a robot is disabled; UI button state is not the safety boundary.

Direct `.script` execution can bypass Dashboard load/readiness checks and may command
motion immediately. Play is sent once: the application does not retry it or
automatically unlock protective stops. Upload success and Dashboard Load success do
not prove that a program is safe or ready to move.

Robot filesystem operations are limited to `/programs`, `/ursim/programs`, and
`/ursim/programs.UR5`. Path traversal, control characters, and destructive operations
on those roots are rejected. This lexical boundary does not replace controller-side
permissions; operators must ensure those roots do not contain unsafe symlinks.

The FastAPI UI has no authentication or CSRF protection. Its trust boundary is one
trusted local operator on `127.0.0.1`. Do not expose it through a reverse proxy or bind
it to an untrusted network. Non-local SSH connections require a previously trusted
host key; automatic host-key acceptance is limited to localhost URSim.

Automated tests never require or contact a real robot. They cannot validate cell risk
assessment, safety I/O, payload/TCP configuration, guarding, emergency stops, or any
manufacturer-required commissioning procedure.

Report security issues privately to the repository owner rather than opening a
public issue containing exploit details or credentials.
