FROM universalrobots/ursim_e-series

USER root

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server python3 && \
    mkdir -p /run/sshd /urcaps && \
    sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin yes/' /etc/ssh/sshd_config && \
    sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication yes/' /etc/ssh/sshd_config && \
    echo 'root:easybot' | chpasswd && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

COPY mock_robotiq_gripper.py /opt/uram/mock_robotiq_gripper.py
COPY start_mock_robotiq.sh /opt/uram/start_mock_robotiq.sh

RUN chmod +x /opt/uram/mock_robotiq_gripper.py /opt/uram/start_mock_robotiq.sh
