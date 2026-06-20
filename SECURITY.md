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

Report security issues privately to the repository owner rather than opening a
public issue containing exploit details or credentials.
