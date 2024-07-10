#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Checks an Openstack cluster's rabbit pcs status and warns if the rabbitmq resource has any nodes out
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

CTRLS=(ctrl.ip.0.x, ctrl.ip.0.y, ctrl.ip.0.z)
HOST=${CTRLS[$RANDOM % ${#CTRLS[@]}]}

ch=$(ssh $HOST 'sudo /usr/sbin/pcs status | grep rabbitmq-cluster | grep -v Started | wc -l')
rs=$(ssh $HOST 'sudo /usr/sbin/pcs status | grep rabbitmq-cluster')

if [ "$ch" == 0 ]

then

echo "[OK] rabbitmq-cluster - all nodes up"
echo "$rs" | awk '{print $1": "$3" "$4}'
exit 0

else

echo "[CRITICAL] rabbitmq-cluster $ch nodes down"
echo "$rs" | awk '{print $1": "$3" "$4}'
exit 2
fi
