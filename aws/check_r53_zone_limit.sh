#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Checks an AWS Route 53 zone to see how lose you are to the max-limit of records
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

#echo "$@" > /tmp/commandargs
# Defaults

DEFAULT_WARNPCT="67"
DEFAULT_CRITPCT="34"

# Usage Function

function usage {
  echo "$(basename $0) usage: "
  echo "  [ -w percentage usage which triggers a warning ]"
  echo "  [ -c percentage usage which triggers a critical ]"
  echo "  [ -p aws profile for use with access ]"
  echo "  [ -z Route 53 Hosted Zone ID ]"
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
      WARNPCT="$2"
      shift
      ;;
      -c)
      CRITPCT="$2"
      shift
      ;;
      -p)
      AWSPROFILENAME="$2"
      shift
      ;;
      -z)
      AWSR53ZONEID="$2"
      shift
      ;;
      *)
      usage
      ;;
  esac
  shift
done

# Set default percentages if not set in the call

WARNPERCENTAGE=${WARNPCT:-$DEFAULT_WARNPCT}  # Must be an integer between 0 and 100
CRITPERCENTAGE=${CRITPCT:-$DEFAULT_CRITPCT}  # Must be an integer between 0 and 100 - must be less than WARNPERCENTAGE

[ -n "${AWSPROFILENAME}" ] && [ -n "${AWSR53ZONEID}" ] || usage

### Exit unknown if Critical percentages are above Warn percentages

if [ "$WARNPERCENTAGE" -ge "$CRITPERCENTAGE" ]
then
  echo "[UNKNOWN] - Critical % [$CRITPERCENTAGE] is not more than the Warn % [$WARNPERCENTAGE]"
  exit 3;
fi

### Grab the data to be processed from the appropriate location

if [[ ${HOST} ]]; then
	VALUES=$(ssh ${SSHUSER:-$USER}@${HOST} "aws --profile ${AWSPROFILENAME} route53 get-hosted-zone-limit --hosted-zone-id ${AWSR53ZONEID} --type MAX_RRSETS_BY_ZONE" | jq ". | \"\(.Count) \(.Limit.Value)\"" | sed 's/"//g')
else
	VALUES=$(aws --profile ${AWSPROFILENAME} route53 get-hosted-zone-limit --hosted-zone-id ${AWSR53ZONEID} --type MAX_RRSETS_BY_ZONE | jq ". | \"\(.Count) \(.Limit.Value)\"" | sed 's/"//g')
fi

read RECORDCOUNT RECORDLIMIT <<< ${VALUES}

PERCENTAGE=$(echo print "100*${RECORDCOUNT}/${RECORDLIMIT}" | perl)

if (( $(echo "$CRITPERCENTAGE < $PERCENTAGE" |bc -l) ))
then
	echo -e "[CRITICAL] (AWS Account $AWSR53ZONEID has $RECORDCOUNT Route53 records with a limit of $RECORDLIMIT: ${PERCENTAGE}% used)"
	exit 2; 

# elIf Warn count is > 0, 

elif (( $(echo "$WARNPERCENTAGE < $PERCENTAGE" |bc -l) ))
then
	echo -e "[WARNING] (AWS Account $AWSR53ZONEID has $RECORDCOUNT Route53 records with a limit of $RECORDLIMIT: ${PERCENTAGE}% used)"
	exit 1; 

# else Return OK;

else
	echo -e "[OK] (AWS Account $AWSR53ZONEID has $RECORDCOUNT Route53 records with a limit of $RECORDLIMIT: ${PERCENTAGE}% used)"
	exit 0; 
fi

