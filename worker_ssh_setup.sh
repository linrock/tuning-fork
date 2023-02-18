#!/bin/bash

apt install openssh-server
sed -i 's/#PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
mkdir /run/sshd
/usr/sbin/sshd
