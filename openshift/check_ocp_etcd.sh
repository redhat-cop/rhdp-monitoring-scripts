#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: etcd has a hardcoded limit of 8GB size.  When it is reached, your cluser is nearly unrecoverable and this attempts to check the etcd status
#              (Yes, we hit 7.4GB in the cluster etcd once. Why? Because we like to do unspeakable things to our infrastructure, apparently.)
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

#echo "$@" > /tmp/commandargs
# Defaults

DEFAULT_ETCDWARNPCT="75"
DEFAULT_ETCDCRITPCT="90"
CRITCOUNT=0
WARNCOUNT=0
EXPECTED_ETCD_COUNT=3

# Usage Function

function usage {
  echo "$(basename $0) usage: "
  echo "  [ -w etcd db used warning % ] #(int between 0 and 100) - defaults to 75 must be less than crit percentage"
  echo "  [ -c etcd db used critical % ] #(int between 0 and 100) - defaults to 90"
  echo "  [ -f remote_host ]"
  echo "  [ -s remote_user ]"
  echo ""
  exit 1
}

human_print(){
  while read B dummy; do
    [ $B -lt 1024 ] && echo ${B} B && break
    KB=$(awk "BEGIN {OFMT=\"%.03f\"; print ($B+512)/1024}")
    KBint=$(awk "BEGIN {OFMT=\"%f\"; print int(($B+512)/1024)}")
    [ $KBint -lt 1024 ] && echo ${KB} KiB && break
    MB=$(awk "BEGIN {OFMT=\".03%f\"; print ($KB+512)/1024}")
    MBint=$(awk "BEGIN {OFMT=\"%f\"; print int(($KB+512)/1024)}")
    [ $MBint -lt 1024 ] && echo ${MB} MiB && break
    GB=$(awk "BEGIN {OFMT=\".03%f\"; print ($MB+512)/1024}")
    GBint=$(awk "BEGIN {OFMT=\"%f\"; print int(($MB+512)/1024)}")
    [ $GBint -lt 1024 ] && echo ${GB} GiB && break
    TB=$(awk "BEGIN {OFMT=\"%.03f\"; print ($GB+512)/1024}")
    echo $TB TiB
  done
}

# Set variables by flags

while [[ $# -gt 1 ]]
do
    key="$1"
    case $key in
      -s)
      SSHUSER="$2"
      shift
      ;;
      -f)
      HOST="$2"
      shift
      ;;
      -w)
      ETCDWARNPCT="$2"
      shift
      ;;
      -c)
      ETCDCRITPCT="$2"
      shift
      ;;
      *)
      usage
      USELESSVALUE="$2"
      exit 1;
      shift
      ;;
  esac
  shift
done

# Set default percentages if not set in the call

ETCDWARNPERCENTAGE=${ETCDWARNPCT:-$DEFAULT_ETCDWARNPCT}  # Must be an integer between 0 and 100
ETCDCRITPERCENTAGE=${ETCDCRITPCT:-$DEFAULT_ETCDCRITPCT}  # Must be an integer between 0 and 100 - must be less than WARNPERCENTAGE


### Exit unknown if Critical percentages are above Warn percentages

if [ "$ETCDWARNPERCENTAGE" -ge "$ETCDCRITPERCENTAGE" ]
then
  echo "[UNKNOWN] - ETCD Critical % [$ETCDCRITPERCENTAGE] is not more than the Warn % [$ETCDWARNPERCENTAGE]"
  exit 3;
fi

### Grab the data to be processed from the appropriate location

if [[ ${HOST} ]]; then
  ETCDNODES=$(ssh ${SSHUSER:-$USER}@${HOST} 'oc get nodes --selector='node-role.kubernetes.io/master' -o json' | jq -r '.items[] | .metadata.name' | sort )
  ETCDPODS=$(ssh ${SSHUSER:-$USER}@${HOST} 'oc get pods -n openshift-etcd --selector="app=etcd"' | grep -v "^NAME" | sort )
  ETCDPODS_ETCDCTL_DBSIZE=$(echo "$ETCDPODS" | grep Running | head -n 1 | cut -f 1 -d " " | while read podname; do ssh ${SSHUSER:-$USER}@${HOST} "oc rsh -c etcdctl -n openshift-etcd $podname etcdctl endpoint status --write-out=json" ; done | jq -r '.[] | "\(.Endpoint) \(.Status.dbSize)"' | sort | cut -f 2 -d " ")
  ETCDPODS_MAXSIZE_RUNVAL=$(ssh ${SSHUSER:-$USER}@${HOST} 'oc get pods -n openshift-etcd --selector="app=etcd"' | cut -f 1 -d ' ' | grep -v "^NAME" | sort | xargs -I{}  ssh ${SSHUSER:-$USER}@${HOST} oc -c etcdctl -n openshift-etcd exec {} -- env | grep ETCD_QUOTA_BACKEND_BYTES | sed -e 's/ETCD_QUOTA_BACKEND_BYTES=//')
else
  ETCDNODES=$(oc get nodes --selector='node-role.kubernetes.io/master' -o json | jq -r '.items[] | .metadata.name' | sort )
  ETCDPODS=$(oc get pods -n openshift-etcd --selector="app=etcd" | grep -v "^NAME" | sort )
  ETCDPODS_ETCDCTL_DBSIZE=$(echo "$ETCDPODS" | grep Running | head -n 1 | cut -f 1 -d " " | while read podname; do oc rsh -c etcdctl -n openshift-etcd $podname etcdctl endpoint status --write-out=json ; done | jq -r '.[] | "\(.Endpoint) \(.Status.dbSize)"' | sort | cut -f 2 -d " ")
  ETCDPODS_MAXSIZE_RUNVAL=$(oc get pods -n openshift-etcd --selector="app=etcd" | cut -f 1 -d ' ' | grep -v "^NAME" | sort | xargs -I{} oc -c etcdctl -n openshift-etcd exec {} -- env | grep ETCD_QUOTA_BACKEND_BYTES | sed -e 's/ETCD_QUOTA_BACKEND_BYTES=//')
fi
 
PRIMARY_OUTPUT=$(paste <(echo "$ETCDNODES") <(echo "$ETCDPODS_MAXSIZE_RUNVAL") <(echo "$ETCDPODS_ETCDCTL_DBSIZE"))


### Process and obtain all detail out of the ALLNODES variable
COUNTNODES=$(echo "${ETCDNODES}" | wc -l)
COUNTPODS=$(echo "${ETCDPODS}" | wc -l)

STATUS_LINE=""

### Check each condition and increment the Relevant Critical and warn conditions
#
#
CRITCOUNT=0
WARNCOUNT=0
  # Confirm the Etcd node count (master/controlplane) against etcd pod count
  # 
  #
  if [[ "$COUNTNODES" -eq "$EXPECTED_ETCD_COUNT" ]] 
  then
    let "OKCOUNT++"
    NODECOUNT_STATUS="OK"
  elif [[ "$COUNTNODES" -eq 2 ]]
  then
    let "WARNCOUNT++"
    NODECOUNT_STATUS="WARN"
  else
    let "CRITCOUNT++"
    NODECOUNT_STATUS="CRIT"
  fi

  if [[ "$COUNTPODS" -eq "$EXPECTED_ETCD_COUNT" ]] 
  then
    let "OKCOUNT++"
    PODCOUNT_STATUS="OK"
  elif [[ "$COUNTPODS" -eq 2 ]]
  then
    let "WARNCOUNT++"
    PODCOUNT_STATUS="WARN"
  else
    let "CRITCOUNT++"
    PODCOUNT_STATUS="CRIT"
  fi

# Run individual Node Checks

while read NODE MAX_SIZE_RUNNING CURR_SIZE_ETCDCTL; do
  STATUS_LINE="${STATUS_LINE}${NODE}:"
  # Calculate Warn and Crit DB Percentage sizes
  #  (We will use the Running size, more than the file size)
  #
  CRIT_DB_SIZE=$(awk "BEGIN {OFMT=\"%f\"; print int($MAX_SIZE_RUNNING*($ETCDCRITPERCENTAGE/100))}")
  WARN_DB_SIZE=$(awk "BEGIN {OFMT=\"%f\"; print int($MAX_SIZE_RUNNING*($ETCDWARNPERCENTAGE/100))}")
  
  HUMAN_CURR_SIZE_ETCDCTL=$( numfmt --to='iec-i' --format='%-2f' $CURR_SIZE_ETCDCTL )
  HUMAN_MAX_SIZE_RUNNING=$( numfmt --to='iec-i' --format='%-2f' $MAX_SIZE_RUNNING )

  # Check how close etcd is to maxing out its size 
  if [[ "$CURR_SIZE_ETCDCTL" -ge "$CRIT_DB_SIZE" ]] 
  then
    let "CRITCOUNT++"
    STATUS_LINE="${STATUS_LINE} CRIT:Over${ETCDCRITPERCENTAGE}%:EtcdSize (Current: $HUMAN_CURR_SIZE_ETCDCTL), Max: $HUMAN_MAX_SIZE_RUNNING)\n"
  elif [[ "$CURR_SIZE_ETCDCTL" -ge "$WARN_DB_SIZE" ]]
  then
    let "WARNCOUNT++"
    STATUS_LINE="${STATUS_LINE} WARN:Over${ETCDWARNPERCENTAGE}%:EtcdSize (Current: $HUMAN_CURR_SIZE_ETCDCTL, Max: $HUMAN_MAX_SIZE_RUNNING)\n"
  else
    STATUS_LINE="${STATUS_LINE} OK:EtcdSize (Current: $HUMAN_CURR_SIZE_ETCDCTL, Max: $HUMAN_MAX_SIZE_RUNNING)\n"
  fi
done  <<< "$PRIMARY_OUTPUT"


# If Crit count is > 0, run critical output

if [ "$CRITCOUNT" -gt "0" ]
then
  echo -e "[CRITICAL] - OCP ETCD Monitor fail with $COUNTNODES nodes and $COUNTPODS pods of $EXPECTED_ETCD_COUNT expected\n$STATUS_LINE"
  exit 2; 

# elIf Warn count is > 0, 

elif [ "$WARNCOUNT" -gt "0" ]
then
  echo -e "[WARNING] - OCP ETCD Monitor fail with $COUNTNODES nodes and $COUNTPODS pods of $EXPECTED_ETCD_COUNT expected\n$STATUS_LINE"
  exit 1; 

# else Return OK;

else
  echo -e "[OK] - OCP ETCD Monitor OK with $COUNTNODES nodes and $COUNTPODS pods of $EXPECTED_ETCD_COUNT expected\n$STATUS_LINE"
  exit 0; 
fi
