#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Checks Anarchy Runs for bad states so operations can investigate and resolve
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

#echo "$@" > /tmp/commandargs
# Defaults
IFS_BAK=$IFS 
DEFAULT_WARNLEVEL=3
DEFAULT_CRITLEVEL=72
WARNCOUNT=0
CRITCOUNT=0
DEEPLINKURLPREFIX='https://my.babylon-ui.example.com'
DEEPLINKURLSUFFIX='/admin/anarchyruns'
DEEPLINKURL="${DEEPLINKURLPREFIX}${DEEPLINKURLSUFFIX}"

# Setup Namespace links - this needs to be adjusted for
# each new governor and namespace created
# Unfortunately, most items are not set in their respective
# namespaces, yet, so I have no way to programatically
# determine the namespace from the name.
#declare -A nstoaccount
#nstoaccount["ansiblebu."]="babylon-anarchy-ansiblebu"
#nstoaccount["appsvc."]="babylon-anarchy-appsvc"
#nstoaccount["azure."]=""
#nstoaccount["test."]="babylon-anarchy-test"


# BaseURL of test instance ocp-us-east-1.infra.open.redhat.com
# Usage Function

function usage {
  echo "$(basename $0) usage: "
  echo "  [ -w number of failed entries before warn ]" 
  echo "  [ -c max entry age before crit ]"
  echo "  [ -f remote_host ]"
  echo "  [ -s remote_user ]"
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
      *)
      usage
      ;;
  esac
  shift
done

# Set default levels if not set in the call
WARNLEVEL=${WARNLEVEL:-$DEFAULT_WARNLEVEL}  # Must be an integer between 0 and 100
CRITLEVEL=${CRITLEVEL:-$DEFAULT_CRITLEVEL}  # Must be an integer between 0 and 100
SSHUSER=${SSHUSER:-$USER}

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
# openstack.novello-smart-management-foundations.prod-mghj4-4s5xp mghj4 openstack.novello-smart-management-foundations.prod 2021-02-22T18:20:15Z
# openstack.novello-smart-management-foundations.prod-rvhk6-hjbvq rvhk6 openstack.novello-smart-management-foundations.prod 2021-02-16T14:04:04Z
# openstack.novello-smart-management-foundations.prod-trqhs-k8tls trqhs openstack.novello-smart-management-foundations.prod 2021-02-15T18:27:31Z
#
if [[ ${HOST} ]]; then
  PRIMARYOUTPUT=$(ssh -n ${SSHUSER}@${HOST} "oc get anarchyrun --all-namespaces -l anarchy.gpte.redhat.com/runner=failed -o json" | jq ".items[] | \"\(.metadata.namespace) \(.metadata.name) \(.spec.subject.vars.job_vars.guid) \(.spec.governor.name) \(.metadata.creationTimestamp)\"" | sed 's/["\]//g')
else
  PRIMARYOUTPUT=$(oc get anarchyrun --all-namespaces -l anarchy.gpte.redhat.com/runner=failed -o json | jq ".items[] | \"\(.metadata.namespace) \(.metadata.name) \(.spec.subject.vars.job_vars.guid) \(.spec.governor.name) \(.metadata.creationTimestamp)\"" | sed 's/["\]//g')
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
PRETTYPRINT=''
while read -r namespace runname guid governor iso8601; do
    # Get the CFME ID, based on whether the HOST is defined for remote SSH or run locally
    # We get some Babylon entries here that aren't parseable - live example output.  The Null, will turn into "gitops-null" as config items do not have a GUID per se.  We need to ignore these.
    # anarchy-k8s-config               babylon-configure-nwxqm-hxhzw                        null  gitops                            2021-11-05T17:02:47Z
    # anarchy-operator                 gpte.ocp4-workshop-shadowman.test-27mgm-create-mw2ck 27mgm gpte.ocp4-workshop-shadowman.test 2021-11-09T21:28:41Z
    # openstack.novello-smart-management-foundations.prod-bd8u

    # Idio, we skip things from anarchy-k8s-config
    if [[ "${namespace}" == "anarchy-k8s-config" ]]; then
      continue;
    fi

    ### OUTPUT
    # openstack.novello-smart-management-foundations.prod-bd89
    if [[ ${HOST} ]]; then
      CFMEGUIDRAW=$(ssh -n $SSHUSER@$HOST "oc get anarchysubject -n $namespace $governor-$guid -o custom-columns='NAMESPACE:.metadata.annotations.poolboy\.gpte\.redhat\.com/resource-claim-namespace,NAME:.metadata.annotations.poolboy\.gpte\.redhat\.com/resource-claim-name'" | tail -n 1 | awk '{print $2}')
    else
      CFMEGUIDRAW=$(oc get anarchysubject -n $namespace $governor-$guid -o custom-columns='NAMESPACE:.metadata.annotations.poolboy\.gpte\.redhat\.com/resource-claim-namespace,NAME:.metadata.annotations.poolboy\.gpte\.redhat\.com/resource-claim-name' | tail -n 1 | awk '{print $2}')
    fi
    CFMEGUIDCLEAN=$(echo $CFMEGUIDRAW | sed "s/$governor-//")
    OUREPOCH=$(date -d $iso8601 +%s)
    let DIFF=$CURRENTEPOCH-$OUREPOCH
    let HOURS=$DIFF/3600
    PRETTYPRINT="$PRETTYPRINT$namespace $runname $guid $CFMEGUIDCLEAN ${HOURS}hrs;"$'\n'
done <<< "$PRIMARYOUTPUT"

## Make sure you reset the IFS or else the next read will fail to separate the variables
IFS=$IFS_BAK
PRETTYPRINT=$(echo "$PRETTYPRINT" | sed 'N;$s/\n//') # remove the final newline on the output so we don't get extra entries in future templates
COUNT=$(echo "$PRIMARYOUTPUT" | grep -v anarchy-k8s-config | wc -l)

MAXHOURS=0
# Count the number of hours which exceed critical level
# Separate lines based on the semicolon we entered here.
while read -r namespace runname guid cfmeguid iso8601; do
    MYHOURS=$(echo $iso8601 | sed 's/hrs;$//')
    if [[ "$MYHOURS" -ge "$CRITLEVEL" ]]; then
        (( CRITCOUNT++ )) # Force critical if any of the hours old exceed the critical limit
        if [[ "$MYHOURS" -gt "$MAXHOURS" ]]; then
           MAXHOURS=$MYHOURS
        fi
    fi
done  <<< "$PRETTYPRINT"

sleep 1;
### Check each condition and increment the Relevant Critical and warn conditions

if [[ "$COUNT" -ge "$WARNLEVEL"  ]]
then
  (( WARNCOUNT++ ))
fi

sleep 1;

#Prepare the Hyperlinks in the output if there's a baseurl specified
PRETTYHYPERLINKS=''
while read -r namespace runname guid governor iso8601; do
   if [ -z ${DEEPLINKURL+x} ]; # Validate that the DEEPLINKBASEURL has been set, and do not hyperlink if it is not set
   then
       PRETTYHYPERLINKS="$PRETTYHYPERLINKS $namespace $runname $guid $governor $iso8601"$'\n'
   else
       PRETTYHYPERLINKS="$PRETTYHYPERLINKS<a target=\"_blank\" href=\"$DEEPLINKURL/$namespace/$runname\">$namespace $runname</a> $guid $governor $iso8601<br />"$'\n'
   fi
done  <<< "$PRETTYPRINT"


# Test each condition and return the appropriate output.

# If Crit count is > 0, run critical output

if [[ "$CRITCOUNT" -gt "0" ]]
then
  echo -e "[CRITICAL] Anarchy failure has exceeded or matches max age of $CRITLEVEL hours at $MAXHOURS hours; | anarchyfailed=$COUNT\n${PRETTYHYPERLINKS}\n"
  exit 2;

# elIf Warn count is > 0, 

elif [[ "$WARNCOUNT" -gt "0" ]]
then
  echo -e "[WARNING] Number of failed Anarchy builds matches or exceeds $WARNLEVEL at $COUNT failed;| anarchyfailed=$COUNT\n${PRETTYHYPERLINKS}\n"
  exit 1;

# else Return OK;

else
  echo -e "[OK] Number of failed Anarchy builds does not exceed $WARNLEVEL at $COUNT failed;| anarchyfailed=$COUNT\n${PRETTYHYPERLINKS}\n"
  exit 0;
fi

