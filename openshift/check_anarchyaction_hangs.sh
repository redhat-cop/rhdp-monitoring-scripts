#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Checks Anarchy Actions for a hung state
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

# Defaults
IFS_BAK=$IFS 
DEFAULT_WARNLEVEL=3
DEFAULT_CRITLEVEL=72
DEFAULT_MINUTES_ACTION_AGE=30
#DEEPLINKURLPREFIX='https://my.babylon-ui.example.com'
#DEEPLINKURLSUFFIX='/admin/anarchyruns/anarchy-operator/'
#DEEPLINKURLSUFFIX='/admin/anarchyactions?search='
#DEEPLINKURL="${DEEPLINKURLPREFIX}${DEEPLINKURLSUFFIX}"

# BaseURL of test instance ocp-us-east-1.infra.open.redhat.com
# Usage Function

function usage {
  echo "$(basename $0) usage: "
  echo "  [ -w number of failed entries before warn ]" 
  echo "  [ -c max entry age before crit ]"
  echo "  [ -f remote_host ]"
  echo "  [ -s remote_user ]"
  echo "  [ -u https baseurl for openshift including port - e.g. https://api.example.com:6443 is 'example.com' ]"
  echo "  [ -p https port for openshift including port ]"
  echo "  [ -x age-in-minutes for the run-after date for the run to be considered hung ]"
#  echo "  ([ -b deep-link-cluster-base-url ])"
  echo ""
  exit 1
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
      WARNLEVEL="$2"
      shift
      ;;
      -c)
      CRITLEVEL="$2"
      shift
      ;;
      #-b)
      #DEEPLINKBASEURL="$2"
      #DEEPLINKURL="${DEEPLINKURLPREFIX}${DEEPLINKURLSUFFIX}"
      #shift
      #;;
      -u)
      OCPAPIBASEURL="$2"
      shift
      ;;
      -p)
      OCPAPIPORT="$2"
      shift
      ;;
      -x)
      AGE_IS_FAILED_MINUTES="$2"
      shift
      ;;
      *)
      usage
      ;;
  esac
  shift
done

if [ -z ${OCPAPIBASEURL+x} ]; then usage; fi
if [ -z ${OCPAPIPORT+x} ]; then usage; fi


# Set default levels if not set in the call
WARNLEVEL=${WARNLEVEL:-$DEFAULT_WARNLEVEL}  # Must be an integer between 0 and 100
CRITLEVEL=${CRITLEVEL:-$DEFAULT_CRITLEVEL}  # Must be an integer between 0 and 100
SSHUSER=${SSHUSER:-$USER}
AGE_IS_FAILED_MINUTES=${AGE_IS_FAILED_MINUTES:-$DEFAULT_MINUTES_ACTION_AGE}
AGE_IS_FAILED_EPOCHTIME=$(( $AGE_IS_FAILED_MINUTES * 60 ))

# Validate SSH connectivity, and validate that anarchy has resources on this cluster
if [[ ${HOST} ]]; then
  ### VALIDATE SSH CONNECTIVITY, return 3 UNKNOWN if SSH connection fails
  ssh -n ${SSHUSER}@${HOST} "ls" > /dev/null
  SSHRETVAL=$?
  if [[ "$SSHRETVAL" != "0" ]]; then
     echo "[UNKNOWN] ssh connection failing"
     exit 3;
  fi

  ### VALIDATE Anarchy is running, return 0 OK if SSH connection fails
  ssh -n ${SSHUSER}@${HOST} "oc get anarchyrun --all-namespaces 2>&1 | grep \"No resources found\"" > /dev/null
  SSHRETVAL=$?
  if [[ "$SSHRETVAL" != "1" ]]; then
     echo "[OK] anarchy is not running on this cluster currently;| anarchyfailed=0"
     exit 0;
  fi
fi

# Pull the primary input from the OC host - use SSH if the HOST variable is defined, else use a local command.
### OUTPUT should look like
# anarchy-operator azure-gpte.ocp4-on-azure-iaas.prod-tgc68-provision-b6tpt 2022-03-10T17:46:03Z azure-gpte.ocp4-on-azure-iaas.prod-tgc68-provision-b6tpt-cgdh54
# anarchy-operator azure-gpte.open-environment-azure.prod-qqfnq-provision-r54mf 2022-03-10T15:37:57Z azure-gpte.open-environment-azure.prod-qqfnq-provision-r5428dst
# anarchy-operator gpte.ilt-ocp4-adv-app-deploy-final-lab-vm.dev-8jl7w-destro559wj 2022-07-13T04:07:59Z gpte.ilt-ocp4-adv-app-deploy-final-lab-vm.dev-8jl7w-destroccz9b
#
if [[ ${HOST} ]]; then
  PRIMARYOUTPUT=$(ssh -n ${SSHUSER}@${HOST} "oc --insecure-skip-tls-verify=true --token=\"$(cat ~/secrets/.ocp-token.api.${OCPAPIBASEURL})\" --server=https://api.${OCPAPIBASEURL}:${OCPAPIPORT} get anarchyaction --all-namespaces -o custom-columns=NAMESPACE:metadata.namespace,NAME:metadata.name,AFTER:spec.after,RUN:status.runRef.name" | sed '1d' | grep -v status | awk '{print $1, $2, $3, $4}')
else
  PRIMARYOUTPUT=$( oc --insecure-skip-tls-verify=true --token="$(cat ~/secrets/.ocp-token.api.${OCPAPIBASEURL})" --server=https://api.${OCPAPIBASEURL}:${OCPAPIPORT} get anarchyaction --all-namespaces -o custom-columns=NAMESPACE:metadata.namespace,NAME:metadata.name,AFTER:spec.after,RUN:status.runRef.name | sed '1d' | grep -v status | awk '{print $1, $2, $3, $4}')
fi

# Check if PRIMARYOUTPUT is blank - if so, immediately drop out as OK

VAR=$(echo $PRIMARYOUTPUT | grep -q '^$')
PRIMARYOUTPUT_EMPTY=$?
if [[ "$PRIMARYOUTPUT_EMPTY" -eq "0" ]]; then
  echo -e "[OK] Number of failed Anarchy builds does not exceed $WARNLEVEL at 0 failed;| anarchyfailed=0\n\n"
  exit 0;
fi



CURRENTEPOCH=$(date +%s)
COUNT=0
NON_HUNG_NULL_ERRORS=0
HUNGCOUNT=0
EMPTY_DATETIME_COUNT=0
EMPTY_PARENTRUN_COUNT=0
PRETTYPRINT=''
while read aa_namespace aa_name aa_after_datetime aa_parent_anarchyrun; do
    ### EXPECTED INPUT STRING FORMAT EXAMPLE
    # anarchy-operator azure-gpte.ocp4-on-azure-iaas.prod-tgc68-provision-b6tpt 2022-03-10T17:46:03Z azure-gpte.ocp4-on-azure-iaas.prod-tgc68-provision-b6tpt-cgdh54
    # anarchy-operator azure-gpte.open-environment-azure.prod-qqfnq-provision-r54mf 2022-03-10T15:37:57Z azure-gpte.open-environment-azure.prod-qqfnq-provision-r5428dst
    # anarchy-operator gpte.ilt-ocp4-adv-app-deploy-final-lab-vm.dev-8jl7w-destro559wj 2022-07-13T04:07:59Z gpte.ilt-ocp4-adv-app-deploy-final-lab-vm.dev-8jl7w-destroccz9b

    ### Prep Variables for checks
    #
    #
    ERRORED_DATETIME=0
    ERRORED_ACTIONPARENT=0
    ERRORED_HUNG=0
    (( COUNT++ )) # Increment the number of runs
    ### Process Input
    # 1. Determine if the datetime runs is null and register nulls as errors
    # 2. Determine if the anarchy runs are null and register nulls as errors
    # 3. Convert the after datetime to the unix epoch if datestamp is not blank
    # 4. If the run is more than the AGE_IN_MINUTES, count as hung and alert

    # 1. Determine if the datetime runs is null and register nulls as errors
    if [[ "$aa_after_datetime" == "<none>" ]]; then
      ERRORED_DATETIME=1
      (( EMPTY_DATETIME_COUNT++ )) # Increment the number of runs
    fi

    # 2. Determine if the anarchy runs are null and register nulls as errors
    if [[ "$aa_parent_anarchyrun" == "<none>" ]]; then
      ERRORED_ACTIONPARENT=1
      (( EMPTY_PARENTRUN_COUNT++ )) # Increment the number of runs
    fi

    # 3. Convert the after datetime to the unix epoch if datestamp is not blank and determine age in minutes
    # NOTE, the AGE_IN_MINUTES between Current epoch time and the run-after-epoch can be positive or negative
    # If positive, it means that the RUNAFTER time has passed.  If negative, it is still in the future.
    if [[ "$ERRORED_DATETIME" -eq '0' ]] && [[ "$ERRORED_ACTIONPARENT" -eq "1" ]]; then
      RUNAFTEREPOCH=$(date --date="${aa_after_datetime}" +"%s")
      EPOCH_RUN_AGE=$(( $CURRENTEPOCH - $RUNAFTEREPOCH ))

    #   4. If the run is more than the AGE_IN_MINUTES, count as hung and alert
    #   If the age of the run is more than the defined minutes (defaults to 30), count as a hung entry and add for alerting
      if [[ "$EPOCH_RUN_AGE" -gt "$AGE_IS_FAILED_EPOCHTIME" ]]; then
        ERRORED_HUNG=1
        let AGE_IN_MINUTES=$EPOCH_RUN_AGE/60 
        (( HUNGCOUNT++ ))
      fi
    fi

    ### COMMAND OUTPUT Prep for ALARMING
    #
    #
      # aa_namespace aa_name aa_after_datetime aa_parent_anarchyrun
    # If anything errored, include it in the output
    # Our output should look like the following (based on the input example) - headers as:
    # Namespace ActionName Age(minutes) BOOLEAN(Has Parent?)
    # anarchy-operator azure-gpte.ocp4-on-azure-iaas.prod-tgc68-provision-b6tpt 31m 1
    # anarchy-operator azure-gpte.open-environment-azure.prod-qqfnq-provision-r54mf 44m 0
    # anarchy-operator gpte.ilt-ocp4-adv-app-deploy-final-lab-vm.dev-8jl7w-destro559wj 9317m 1
    if   [[ "$ERRORED_HUNG" -eq '1' ]]; then
        PRETTYPRINT="$PRETTYPRINT${aa_namespace} ${aa_name} ${AGE_IN_MINUTES}m ParentNULL;"$'\n'
    elif [[ "$ERRORED_DATETIME" -eq '1' ]] && [[ "$ERRORED_ACTIONPARENT" -eq '1' ]]; then
	(( NON_HUNG_NULL_ERRORS++ ))
        PRETTYPRINT="$PRETTYPRINT${aa_namespace} ${aa_name} NULL_TIME ParentNULL;"$'\n'
    elif [[ "$ERRORED_DATETIME" -eq '1' ]] && [[ "$ERRORED_ACTIONPARENT" -eq '0' ]]; then
	(( NON_HUNG_NULL_ERRORS++ ))
        PRETTYPRINT="$PRETTYPRINT${aa_namespace} ${aa_name} NULL_TIME ParentExists;"$'\n'
    fi
done <<< "$PRIMARYOUTPUT"

## Make sure you reset the IFS or else the next read will fail to separate the variables
IFS=$IFS_BAK
PRETTYPRINT=$(echo "$PRETTYPRINT" | sed 'N;$s/\n//') # remove the final newline on the output so we don't get extra entries in future templates

sleep 1;

### DEEP LINKS are not currently available for these runs - as we have no parsing algorithm
#Prepare the Hyperlinks in the output if there's a baseurl specified
#PRETTYHYPERLINKS=''
#while read w x y z d; do
#   if [ -z ${DEEPLINKURL+x} ]; # Validate that the DEEPLINKBASEURL has been set, and do not hyperlink if it is not set
#   then
#       PRETTYHYPERLINKS="$PRETTYHYPERLINKS $w $x $y $z $d"$'\n'
#   else
#       PRETTYHYPERLINKS="$PRETTYHYPERLINKS<a target=\"_blank\" href=\"$DEEPLINKURL$x\">$w $x</a> $y $z $d<br />"$'\n'
#   fi
#done  <<< "$PRETTYPRINT"


# Test each condition and return the appropriate output.

# If Crit count is > 0, run critical output
#jobcount=${COUNT};;;; maxhrs=${MAXHOURS};;;;

if [[ "$HUNGCOUNT" -gt "0" ]]
then
  echo -e "[CRITICAL] AnarchyActions show $HUNGCOUNT actions that are $AGE_IS_FAILED_MINUTES mins past RUNAFTER datestamp; | actions=$COUNT;;;; hung=$HUNGCOUNT;;;; nullerrors=$NON_HUNG_NULL_ERRORS;;;; nulldate=$EMPTY_DATETIME_COUNT;;;; nullparent=$EMPTY_PARENTRUN_COUNT;;;;\n${PRETTYPRINT}\n"
  exit 2;

# elIf Warn count is > 0, 
elif [[ "$NON_HUNG_NULL_ERRORS" -gt "0" ]]
then
  echo -e "[WARNING] AnarchyActions show $EMPTY_DATETIME_COUNT null dates and $EMPTY_PARENTRUN_COUNT null parents;| actions=$COUNT;;;; hung=$HUNGCOUNT;;;; nullerrors=$NON_HUNG_NULL_ERRORS;;;; nulldate=$EMPTY_DATETIME_COUNT;;;; nullparent=$EMPTY_PARENTRUN_COUNT;;;;\n${PRETTYPRINT}\n"
  exit 1;

# else Return OK;

else
  echo -e "[OK] AnarchyActions show no null values and no hung ages with $COUNT total;| actions=$COUNT;;;; hung=$HUNGCOUNT;;;; nullerrors=$NON_HUNG_NULL_ERRORS;;;; nulldate=$EMPTY_DATETIME_COUNT;;;; nullparent=$EMPTY_PARENTRUN_COUNT;;;;\n${PRETTYPRINT}\n"
  exit 0;
fi
