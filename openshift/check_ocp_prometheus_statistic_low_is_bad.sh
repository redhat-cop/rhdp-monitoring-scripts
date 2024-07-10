#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Checks Anarchy Runs for bad states so operations can investigate and resolve
#              Requires a NetRC setup to allow access to prometheus
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

#echo "$@" > /tmp/commandargs
# Defaults

DEFAULT_NETRC='~/.netrc'
DEFAULT_CRITLEVEL=3
DEFAULT_WARNLEVEL=5
DEFAULT_QUERY='query=count(http_requests_total)'
DEFAULT_LABEL='http_requests_total'
CRITCOUNT=0
WARNCOUNT=0

# Usage Function

function usage {
  echo "$(basename $0) usage: "
  echo "  -u URL for prometheus server endpoint - 'https://prometheus-k8s-openshift-monitoring.apps.example.com/api/v1/query'" 
  echo "  -l label for performance metric Must be a string acceptable by Nagios-perfdata standards - no whitespace allowed"
  echo "  -p prometheus query string like 'query=count(ALERTS{alertstate=\"firing\"})'" 
  echo "  -n curl netrc with credentials for monitored site - must be available to user executing monitors " 
  echo "  [ -w metric value equals or exceeds warn ] defaults to 3 "
  echo "  [ -c metric value equals or exceeds crit ] defaults to 5 must be less than warn count"
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
      -l)
      LABEL="$2"
      shift
      ;;
      -p)
      QUERY="$2"
      shift
      ;;
      -n)
      NETRC="$2"
      shift
      ;;
      -u)
      PROMURL="$2"
      shift
      ;;
      *)
      usage
      shift
      ;;
  esac
  shift
done

# If Crit count is > 0, run critical output

if [[ "$WARNLEVEL" -lt "$CRITLEVEL" ]]
then
  echo -e "[UNKNOWN] warning level of $WARNLEVEL is greater than $CRITLEVEL"
  exit 3;
fi

# Set default levels if not set in the call
# URL is non-optional - fail if not set.
WARNLEVEL=${WARNLEVEL:-$DEFAULT_WARNLEVEL}  # Must be an integer between 0 and 100
CRITLEVEL=${CRITLEVEL:-$DEFAULT_CRITLEVEL}  # Must be an integer between 0 and 100
QUERYVAL=${QUERY:-$DEFAULT_QUERY}  # Must be an escaped string
NETRCVAL=${NETRC:-$DEFAULT_NETRC}  # Must be a file path resolvable by the executing user.
LABELVAL=${LABEL:-$DEFAULT_LABEL}  # Must be a string acceptable by Nagios-perfdata standards

# Run the query against the Prometheus host
### OUTPUT should look like
#
if [[ ${HOST} ]]; then
  PRIMARYOUTPUT=$(ssh $SSHUSER@$HOST "curl -s \"$PROMURL\" --data-urlencode \"$QUERYVAL\" --netrc-file $NETRCVAL" | jq .data.result[0].value[1] 2>/dev/null | sed 's/["\]//g')
else
  PRIMARYOUTPUT=$(curl -s $PROMURL --data-urlencode "$QUERYVAL" --netrc-file $NETRCVAL | jq .data.result[0].value[1] 2>/dev/null | sed 's/["\]//g')
fi

# Prometheus returns "null" if there is no value
if [[ "$PRIMARYOUTPUT" == '' ]]; 
then
  PRIMARYOUTPUT=0
fi

### Check each condition and increment the Relevant Critical and warn conditions

if [[ "$PRIMARYOUTPUT" -le "$CRITLEVEL"  ]]
then
  (( CRITCOUNT++ ))
fi

### Check each condition and increment the Relevant Critical and warn conditions

if [[ "$PRIMARYOUTPUT" -le "$WARNLEVEL"  ]]
then
  (( WARNCOUNT++ ))
fi

sleep 1;

# Test each condition and return the appropriate output.

# If Crit count is > 0, run critical output

if [[ "$CRITCOUNT" -gt "0" ]]
then
  echo -e "[CRITICAL] prometheus metric is at or below critical level $CRITLEVEL at $PRIMARYOUTPUT; | $LABELVAL=$PRIMARYOUTPUT\n"
  exit 2;

# elIf Warn count is > 0, 

elif [[ "$WARNCOUNT" -gt "0" ]]
then
  echo -e "[WARNING] prometheus metric is at or below warning level $WARNLEVEL at $PRIMARYOUTPUT;| $LABELVAL=$PRIMARYOUTPUT\n"
  exit 1;

# else Return OK;

else
  echo -e "[OK] prometheus metric is above $WARNLEVEL at $PRIMARYOUTPUT ;| $LABELVAL=$PRIMARYOUTPUT\n"
  exit 0;
fi
