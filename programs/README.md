# Example URScript programs

These small programs are safe repository examples for the direct `.script`
workflow. They do not depend on a URCap or a physical gripper.

- `robot1/demo_hello.script` displays a popup.
- `robot2/demo_idle.script` writes a log message.
- `simulation_demo/ursim_no_gripper_demo.script` runs a five-second, motionless
  popup/log demonstration with no installation or URCap dependency.

Direct script execution is separate from the Dashboard `.urp` workflow: it sends
URScript to the configured script socket and does not deploy or load a PolyScope
project.
