#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Checks Openshift's Cluster Operators for issues
#              If running remotely, expects the monitoring user's token to be stored in the local mon user at ~/tokens/.api.${BASEURL}
# License: Apache License v2
# Output: Nagios/Icinga2 format
###


#echo "$@" > /tmp/commandargs
# Defaults

DEFAULT_WARNDEGRADEDCOUNT=0
DEFAULT_UNAVAILABLECRITCOUNT=0
WARNCOUNT=0
CRITCOUNT=0
TLSVERIFY="false" #Default to false
HTTPPORT=6443
### To add an entry to the minor operators that cannot be critical
#   Add a list entry by adding a space, then double-quoting the operator name.
#   Ex: OPS_DEFINED_MINOR_OPERATORS=("image-registry" "kube-apiserver")
OPS_DEFINED_MINOR_OPERATORS=("image-registry")

# Usage Function

function usage {
  echo "$(basename $0) usage: "
  echo "  [ -w allowed degraded operators ] # number of operators in degraded state before WARN"
  echo "  [ -c allowed unavailable operators ] # number of operators in unavailable state before CRIT" 
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
      WARNDEGRADED="$2"
      shift
      ;;
      -c)
      CRITUNAVAILABLE="$2"
      shift
      ;;
      *)
      usage
      shift
      ;;
  esac
  shift
done

# Set default levels if not set in the call
WARNDEGRADEDCOUNT=${WARNDEGRADED:-$DEFAULT_WARNDEGRADEDCOUNT}  # Must be an integer between 0 and 100
UNAVAILABLECRITCOUNT=${CRITUNAVAILABLE:-$DEFAULT_UNAVAILABLECRITCOUNT}  # Must be an integer between 0 and 100


### Grab the data to be processed from the appropriate location

if [[ ${HOST} ]]; then
  CLEANOUTPUT=$(ssh ${SSHUSER:-$USER}@${HOST} "oc get clusteroperators" | grep -v VERSION | awk '{print $1": "$3, $5, $2";"}' | sort -k 1)
else
  if [[ ${BASEURL} ]]; then
    CLEANOUTPUT=$(oc --insecure-skip-tls-verify="${TLSVERIFY}" --token="$(cat ~/tokens/.api.${BASEURL})" --server="https://api.${BASEURL}:${HTTPPORT}" get clusteroperators  2>/dev/null | grep -v VERSION | awk '{print $1": "$3, $5, $2";"}' | sort -k 1)
  else
    CLEANOUTPUT=$(oc get clusteroperators | grep -v VERSION | awk '{print $1": "$3, $5, $2";"}' | sort -k 1)
  fi
fi

### Process and obtain all detail out of the CLEANOUTPUT variable
PRETTYPRINT=$(echo -n "${CLEANOUTPUT}" | sed -e 's/: True/: Available/' -e 's/: False/: Unavailable/' -e 's/vailable False/vailable Operational/' -e 's/vailable True/vailable Degraded/' )

TOTALCOUNT=$(echo "${PRETTYPRINT}" | wc -l)

OPERATIONALAVAILABLE=$(echo -n "${PRETTYPRINT}" | grep -v Unavailable | grep -v Degraded )
OPERATIONAL=$(echo -n "${PRETTYPRINT}" | grep Operational )
AVAILABLE=$(echo -n "${PRETTYPRINT}" | grep Available )
DEGRADED=$(echo -n "${PRETTYPRINT}" | grep Degraded )
UNAVAILABLE=$(echo -n "${PRETTYPRINT}" | grep Unavailable )

### GPTEINFRA-9117 - bbethell requested ability to define "minor operators" where
#                    a critical status is ignored
UNAVAILABLE_MINOR_OPERATORS_IGNORED="${UNAVAILABLE}"
for i in "${OPS_DEFINED_MINOR_OPERATORS[@]}"; do
  LOCALTEMP=''
  LOCALTEMP=$(echo "$UNAVAILABLE_MINOR_OPERATORS_IGNORED" | grep -v "$i")
  UNAVAILABLE_MINOR_OPERATORS_IGNORED="$LOCALTEMP"
done

OPERATIONALAVAILABLECOUNT=$(echo "${OPERATIONALAVAILABLE}" | sed '/^$/d'| awk '{print NR}'| sort -nr | wc -l)
OPERATIONALCOUNT=$(echo "${OPERATIONAL}" | grep Operational | sed '/^$/d'| awk '{print NR}'| sort -nr | wc -l)
AVAILABLECOUNT=$(echo "${AVAILABLE}" | grep Available | sed '/^$/d'| awk '{print NR}'| sort -nr | wc -l)
DEGRADEDCOUNT=$(echo "${DEGRADED}" | sed '/^$/d'| awk '{print NR}'| sort -nr | wc -l)
UNAVAILABLECOUNT=$(echo "${UNAVAILABLE_MINOR_OPERATORS_IGNORED}" | sed '/^$/d'| awk '{print NR}'| sort -nr | wc -l)


sleep 1;
### Check each condition and increment the Relevant Critical and warn conditions

if [[ "$DEGRADEDCOUNT" -gt "$WARNDEGRADEDCOUNT" ]]
then
  let "WARNCOUNT++"
fi

if [[ "$UNAVAILABLECOUNT" -gt "$UNAVAILABLECRITCOUNT" ]]
then
  let "CRITCOUNT++"
fi

sleep 1;

# Test each condition and return the appropriate output.

# If Crit count is > 0, run critical output

if [[ "$CRITCOUNT" -gt 0 ]]
then
  echo -e "[CRITICAL] Operators Unavailable: $UNAVAILABLECOUNT/$TOTALCOUNT, Degraded: $DEGRADEDCOUNT/$TOTALCOUNT;\n${UNAVAILABLE}\n${DEGRADED}"
  exit 2; 

# elIf Warn count is > 0, 

elif [[ "$WARNCOUNT" -gt 0 ]]
then
  echo -e "[WARNING] Operators Unavailable: $UNAVAILABLECOUNT/$TOTALCOUNT, Degraded: $DEGRADEDCOUNT/$TOTALCOUNT;\n${DEGRADED}"
  exit 1; 

# else Return OK;

else
  echo -e "[OK] Operators Available: $AVAILABLECOUNT/$TOTALCOUNT, Operational: $OPERATIONALCOUNT/$TOTALCOUNT;\n${PRETTYPRINT}"
  exit 0; 
fi
