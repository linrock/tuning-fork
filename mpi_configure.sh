#!/bin/bash

SSH_CONFIG=/root/.ssh/config
touch $SSH_CONFIG

while read -r line; do
  server_ip=$(echo $line | awk '{print $1}')
  server_name=$(echo $line | awk '{print $2}')

  if ! grep $server_name $SSH_CONFIG ; then
    echo $server_name not in ssh config. Adding config entry.
    echo "Host $server_name" >> $SSH_CONFIG
    echo "  HostName $server_ip" >> $SSH_CONFIG
    echo "  Port 65022" >> $SSH_CONFIG
    echo >> $SSH_CONFIG
  fi
  echo $server_name
  ssh root@$server_ip "echo hi"
done < hosts
