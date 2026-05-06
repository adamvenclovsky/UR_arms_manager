from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
from xmlrpc.server import SimpleXMLRPCServer


@dataclass
class GripperState:
    activated: bool = True
    connected: bool = True
    position: float = 0.0
    speed: float = 100.0
    force: float = 100.0
    max_current: int = 0
    fault: int = 0
    object_detected: int = 0
    lock: Lock = field(default_factory=Lock)


class RobotiqGripperMock:
    def __init__(self) -> None:
        self.state = GripperState()

    def allowToolComm(self, *_args):
        return True

    def activate(self, *_args):
        with self.state.lock:
            self.state.activated = True
            self.state.connected = True
            self.state.fault = 0
        return True

    def activateIfRequired(self, *_args):
        return self.activate()

    def deactivate(self, *_args):
        with self.state.lock:
            self.state.activated = False
        return True

    def isGripperActivated(self, *_args):
        return self.state.activated

    def isGripperConnected(self, *_args):
        return self.state.connected

    def getFault(self, *_args):
        return self.state.fault

    def getObjectDetectionFlag(self, *_args):
        return self.state.object_detected

    def isObjectDetected(self, *_args):
        return bool(self.state.object_detected)

    def configureVacuum(self, *_args):
        return True

    def goto(self, _slave_id=9, value=0):
        with self.state.lock:
            self.state.position = float(value)
            self.state.object_detected = 1 if self.state.position >= 1 else 0
        return True

    def openGripper(self, *_args):
        with self.state.lock:
            self.state.position = 0.0
            self.state.object_detected = 0
        return True

    def closeGripper(self, *_args):
        with self.state.lock:
            self.state.position = 100.0
            self.state.object_detected = 1
        return True

    def move(self, _slave_ids=None, position=0, *_args):
        with self.state.lock:
            self.state.position = float(position)
            self.state.object_detected = 1 if self.state.position > 0 else 0
        return True

    def getCurrentPosition(self, *_args):
        return self.state.position

    def setForce(self, _slave_ids=None, force=0):
        with self.state.lock:
            self.state.force = float(force)
        return True

    def setSpeed(self, _slave_ids=None, speed=0):
        with self.state.lock:
            self.state.speed = float(speed)
        return True

    def setMaximumCurrent(self, current_mA=0, *_args):
        with self.state.lock:
            self.state.max_current = int(current_mA)
        return True

    def setMaximumCurrentOnAllGrippers(self, current_mA=0):
        with self.state.lock:
            self.state.max_current = int(current_mA)
        return True

    def getMaximumCurrent(self, *_args):
        return self.state.max_current

    def pauseAndDisconnect(self):
        with self.state.lock:
            self.state.connected = False
        return True

    def reconnectAndResume(self, *_args):
        with self.state.lock:
            self.state.connected = True
        return True


def main() -> None:
    server = SimpleXMLRPCServer(
        ("127.0.0.1", 63353),
        allow_none=True,
        logRequests=False,
    )
    server.register_instance(RobotiqGripperMock(), allow_dotted_names=False)
    print("Robotiq gripper mock listening on 127.0.0.1:63353", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
