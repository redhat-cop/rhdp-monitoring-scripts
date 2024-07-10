#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Checks the node status to find any that are not ready
#              If running remotely, expects that your token is stored in the following location for the mon user: ~/tokens/.api.${BASEURL}
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

#echo "$@" > /tmp/commandargs
# Defaults

DEFAULT_MASTERWARNPCT="67"
DEFAULT_WORKERWARNPCT="67"
DEFAULT_MASTERCRITPCT="34"
DEFAULT_WORKERCRITPCT="34"
CRITCOUNT=0
WARNCOUNT=0
TLSVERIFY="false" #Default to true
HTTPPORT=6443

# Usage Function

function usage {
  echo "$(basename $0) usage:"
  echo "  [ -w master online warning Percentage ] #(int between 0 and 100) - defaults to 67 must be greater than master crit percentage"
  echo "  [ -x worker online warning Percentage ] #(int between 0 and 100) - defaults to 67 must be greater than worker crit percentage"
  echo "  [ -c master online critical Percentage ] #(int between 0 and 100) - defaults to 34"
  echo "  [ -d worker online critical Percentage ] #(int between 0 and 100) - defaults to 34"
  echo "  [ -t TLS Verify disable - required for service account tokens ]"
  echo "  [ -p port for the cluster API - e.g. 6443 ]"
  echo "  [ -b base URL of the cluster - e.g. cluster.example.com ]"
  echo "  [ -f remote_host ]"
  echo "  [ -s remote_user ]"
  echo ""
  exit 1
}


# Set variables by flags

while [[ $# -gt 1 ]]
do
    key="$1"
    case $key in
      -t)
      TLSVERIFY="true"
      ;;
      -b)
      BASEURL="$2"
      shift
      ;;
      -p)
      BASEPORT="$2"
      shift
      ;;
      -s)
      SSHUSER="$2"
      shift
      ;;
      -f)
      HOST="$2"
      shift
      ;;
      -w)
      MASTERWARNPCT="$2"
      shift
      ;;
      -x)
      WORKERWARNPCT="$2"
      shift
      ;;
      -c)
      MASTERCRITPCT="$2"
      shift
      ;;
      -d)
      WORKERCRITPCT="$2"
      shift
      ;;
      *)
      usage
      shift
      ;;
  esac
  shift
done

# Set default percentages if not set in the call

MASTER_READY_WARNPERCENTAGE=${MASTERWARNPCT:-$DEFAULT_MASTERWARNPCT}  # Must be an integer between 0 and 100
WORKER_READY_WARNPERCENTAGE=${WORKERWARNPCT:-$DEFAULT_WORKERWARNPCT}  # Must be an integer between 0 and 100
MASTER_READY_CRITPERCENTAGE=${MASTERCRITPCT:-$DEFAULT_MASTERCRITPCT}  # Must be an integer between 0 and 100 - must be less than WARNPERCENTAGE
WORKER_READY_CRITPERCENTAGE=${WORKERCRITPCT:-$DEFAULT_WORKERCRITPCT} # Must be an integer between 0 and 100 - must be less than WARNPERCENTAGE


### Exit unknown if Critical percentages are above Warn percentages

if [ "$MASTER_READY_WARNPERCENTAGE" -le "$MASTER_READY_CRITPERCENTAGE" ]
then
  echo "[UNKNOWN] - Master Critical % [$MASTER_READY_CRITPERCENTAGE] is not less than the Warn % [$MASTER_READY_WARNPERCENTAGE]"
  exit 3;
fi

if [ "$WORKER_READY_WARNPERCENTAGE" -le "$WORKER_READY_CRITPERCENTAGE" ]
then
  echo "[UNKNOWN] - Worker Critical % [$WORKER_READY_CRITPERCENTAGE] is not less than the Warn % [$WORKER_READY_WARNPERCENTAGE]"
  exit 3;
fi

### Grab the data to be processed from the appropriate location

if [[ ${HOST} ]]; then
  ALLNODES=$(ssh ${SSHUSER:-$USER}@${HOST} "oc get nodes" | grep -v VERSION | awk '{print $2": "$3, $1";"}' | sort -r -k 2)
else
  if [[ ${BASEURL} ]]; then
    ALLNODES=$(oc --insecure-skip-tls-verify="${TLSVERIFY}" --token="$(cat ~/tokens/.api.${BASEURL})" --server="https://api.${BASEURL}:${HTTPPORT}" get nodes 2>/dev/null | grep -v VERSION | awk '{print $2": "$3, $1";"}' | sort -r -k 2)
  else
    ALLNODES=$(oc get nodes | grep -v VERSION | awk '{print $2": "$3, $1";"}' | sort -r -k 2)
  fi
fi

### Process and obtain all detail out of the ALLNODES variable
MASTERNODES=$(echo "${ALLNODES}" | grep master)
WORKERNODES=$(echo "${ALLNODES}" | grep -v master)
NODECOUNT=$(echo "${ALLNODES}" | wc -l)
MASTERCOUNT=$(echo "${MASTERNODES}" | wc -l)
WORKERCOUNT=$(echo "${WORKERNODES}" | wc -l)
MASTERREADYCOUNT=$(echo "${MASTERNODES}" | grep "^Ready" | wc -l)
WORKERREADYCOUNT=$(echo "${WORKERNODES}" | grep "^Ready" | wc -l)
MASTERCRITLEVEL=$(echo $(( $MASTERCOUNT*$MASTER_READY_CRITPERCENTAGE/100 )) )
MASTERWARNLEVEL=$(echo $(( $MASTERCOUNT*$MASTER_READY_WARNPERCENTAGE/100 )) )
WORKERCRITLEVEL=$(echo $(( $WORKERCOUNT*$WORKER_READY_CRITPERCENTAGE/100 )) )
WORKERWARNLEVEL=$(echo $(( $WORKERCOUNT*$WORKER_READY_WARNPERCENTAGE/100 )) )


### Check each condition and increment the Relevant Critical and warn conditions

if [ "$WORKERWARNLEVEL" -ge "$WORKERREADYCOUNT" ]
then
  let "WARNCOUNT++"
fi

if [ "$MASTERWARNLEVEL" -ge "$MASTERREADYCOUNT" ]
then
  let "WARNCOUNT++"
fi

if [ "$WORKERCRITLEVEL" -ge "$WORKERREADYCOUNT" ]
then
  let "CRITCOUNT++"
fi

if [ "$MASTERCRITLEVEL" -ge "$MASTERREADYCOUNT" ]
then
  let "CRITCOUNT++"
fi




# Test each condition and return the appropriate output.

# If Crit count is > 0, run critical output

if [ "$CRITCOUNT" -gt "0" ]
then
  echo -e "[CRITICAL] (Master fail $MASTER_READY_CRITPERCENTAGE%/Worker fail $WORKER_READY_CRITPERCENTAGE%) Ready Nodes ($MASTERREADYCOUNT/$WORKERREADYCOUNT), NotReady Nodes $(( $MASTERCOUNT - $MASTERREADYCOUNT ))/$(( $WORKERCOUNT - $WORKERREADYCOUNT ));\n${MASTERNODES}\n${WORKERNODES}\n"
  exit 2; 

# elIf Warn count is > 0, 

elif [ "$WARNCOUNT" -gt "0" ]
then
  echo -e "[WARNING] (Master fail $MASTER_READY_WARNPERCENTAGE%/Worker fail $WORKER_READY_WARNPERCENTAGE%) Ready Nodes ($MASTERREADYCOUNT/$WORKERREADYCOUNT), NotReady Nodes $(( $MASTERCOUNT - $MASTERREADYCOUNT ))/$(( $WORKERCOUNT - $WORKERREADYCOUNT ));\n${MASTERNODES}\n${WORKERNODES}\n"
  exit 1; 

# else Return OK;

else
  echo -e "[OK] (Master/Worker) Ready Nodes ($MASTERREADYCOUNT/$WORKERREADYCOUNT), NotReady Nodes $(( $MASTERCOUNT - $MASTERREADYCOUNT ))/$(( $WORKERCOUNT - $WORKERREADYCOUNT ));\n${MASTERNODES}\n${WORKERNODES}\n"
  exit 0; 
fi

