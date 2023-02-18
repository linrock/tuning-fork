#!/bin/bash

apt install -y openssh-server
sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
mkdir /run/sshd
/usr/sbin/sshd
ps aux | grep sshd
