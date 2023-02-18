#!/bin/bash

apt install -y openssh-server
sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/#Port.*/Port 65022/' /etc/ssh/sshd_config
mkdir /run/sshd
/usr/sbin/sshd
ps aux | grep sshd
