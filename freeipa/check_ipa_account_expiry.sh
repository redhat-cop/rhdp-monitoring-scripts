#!/bin/bash


# Author: jappleii@redhat.com - John Apple II
# Description: Checks the account expiry of any member of the "admins" group and warns on approaching expiry or expired admin-user
#              Any admin who doesn't change their password within a reasonable time likely shouldn't be an admin
# License: Apache License v2
# Output: Nagios/Icinga2 format
###


# Execution examples
# Passive Check (curl)
# check_ipa_account_expiry.sh -l "username" -d "cn=users,cn=accounts,dc=ipa,dc=example,dc=com" -F "(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)" -i /home/icinga/icinga-ipa_infra.crt -j /home/icinga/icinga-ipa_infra.key -c /home/icinga/ca.crt -a https://my.icinga.example.com:5665 -h host.ipa.example.com -x check_idm_user_expiry_admin -p 0
# Active Check
# check_ipa_account_expiry.sh -l "username" -d "cn=users,cn=accounts,dc=ipa,dc=example,dc=com" -F "(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)"


#echo "$@" > /tmp/commandargs
# Defaults
IFS_BAK=$IFS 
GROUP_NAME=""
USER_CSV=""
SYSTEM_USER_CSV=""
HOME_PATH="/home/icinga"
KEYTAB_NAME=monitoring.keytab
KEYTAB_PRINCIPLE_UID="monitoring"
KEYTAB_PRINCIPLE_HOST=`hostname`
SYSTEMACCT_DN="cn=sysaccounts,cn=etc,dc=ipa,dc=example,dc=com"
USERACCT_DN="cn=users,cn=accounts,dc=ipa,dc=example,dc=com"
SELECTED_DN=""
GROUP_FILTER_STRING_DN="(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)"
DEFAULT_WARNLEVEL=10
WARNING_DAYS_IN_SECONDS=""
HOSTNAME="$(hostname)"
PASSIVE_CHECK=1 # Default to active check

# Usage Function

function usage {
  ERR_MESSAGE="$@"
  echo "ERROR: $ERR_MESSAGE"
  echo "$(basename $0) usage: "
  echo "  [ -g group to use for check ]" 
  echo "  [ -l usernames as a csv to check ]"
  echo "  [ -s systemaccounts to check ]"
  echo "  [ -d dn string to use for the item to be checked ]"
  echo "  [ -F filter string for group membership ]"
  echo "  [ -k keytab to be used to authenticate to LDAP ]"
  echo "  [ -K LDAP principle to use in the keytab ]"
  echo "  [ -w number of days left at which to create a warning NOTE: any expired credential counts as a CRITICAL ]"
  echo "  [ -f remote_host ]"
  echo "  [ -s remote_user ]"
  echo "  [ -p ] use a passive check to send the result to Icinga" 
  echo "  [ -h hostname for the passive check ]"
  echo "  [ -x service for the passive check ]"
  echo "  [ -i user certificate for the passive check ]"
  echo "  [ -j user key for the passive check ]"
  echo "  [ -c ca-cert for the passive check ]"
  echo "  [ -a api URL for the passive check ]"
  echo ""
  exit 1
}


# Set variables by flags

while [[ $# -gt 1 ]]
do
    key="$1"
    case $key in
      -g)
      GROUP_NAME="$2"
      shift
      ;;
      -l)
      USER_CSV="$2"
      shift
      ;;
      -s)
      SYSTEM_USER_CSV="$2"
      shift
      ;;
      -d)
      SELECTED_DN="$2"
      shift
      ;;
      -F)
      GROUP_FILTER_STRING_DN="$2"
      shift
      ;;
      -k)
      KEYTAB_NAME="$2"
      shift
      ;;
      -K)
      KEYTAB_PRINCIPLE="$2"
      shift
      ;;
      -f)
      HOST="$2"
      shift
      ;;
      -s)
      SSHUSER="$2"
      shift
      ;;
      -w)
      WARNLEVEL="$2"
      shift
      ;;
      -p)
      PASSIVE_CHECK="0"
      shift
      ;;
      -h)
      PASSIVE_HOST="$2"
      shift
      ;;
      -x)
      PASSIVE_SVC="$2"
      shift
      ;;
      -i)
      PASSIVE_USER_CERT_CERT="$2"
      shift
      ;;
      -j)
      PASSIVE_USER_CERT_KEY="$2"
      shift
      ;;
      -c)
      PASSIVE_CA_CERT="$2"
      shift
      ;;
      -a)
      PASSIVE_API_URL="$2"
      shift
      ;;
      *)
      usage "Unknown option passed"
      USELESSVALUE="$2"
      exit 1;
      shift
      ;;
  esac
  shift
done

[ -z "${GROUP_NAME}" ] && [ -z "${USER_CSV}" ] && [ -z "${SYSTEM_USER_CSV}" ]  && usage "One of -g, -l, or -s are required"


# kinit -t /root/monitoring.keytab -k monitoring/ipa1.ipa.example.com
# ldapwhoami -Y GSSAPI
# SASL/GSSAPI authentication started
# SASL username: monitoring/ipa1.ipa.example.com@ipa.example.com@ipa.example.com
# SASL SSF: 256
# SASL data security layer installed.
# dn: krbprincipalname=monitoring/host.ipa.example.com@ipa.example.com,cn=services,cn=accounts,dc=ipa,dc=example,dc=com
# date --utc +%Y%m%d%H%M%SZ
# ldapsearch -b cn=users,cn=accounts,dc=ipa,dc=example,dc=com -Y GSSAPI - uid krbPasswordExpiration mail
# ldapsearch -b cn=users,cn=accounts,dc=ipa,dc=example,dc=com '(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)' -Y GSSAPI
# ldapsearch -b cn=users,cn=accounts,dc=ipa,dc=example,dc=com '(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)' -Y GSSAPI uid krbPasswordExpiration mail

# Set default levels if not set in the call
WARNLEVEL=${WARNLEVEL:-$DEFAULT_WARNLEVEL}  # Must be an integer between 0 and 100
CRITLEVEL=0 # For this monitor, 0 is the critical level, because it means the account is expired, or will be shortly.
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
fi

# Pull the primary input from the OC host - use SSH if the HOST variable is defined, else use a local command.
### OUTPUT should look like
if [[ ${HOST} ]]; then
  PRIMARYOUTPUT=$(ssh -n ${SSHUSER}@${HOST} "kinit -t ${KEYTAB_NAME} -k ${KEYTAB_PRINCIPLE_UID}/${KEYTAB_PRINCIPLE_HOST} && ldapsearch -b ${SELECTED_DN} ${GROUP_FILTER_STRING_DN} -Y GSSAPI uid krbPasswordExpiration mail -LLL ")
  PRIMARYRETVAL=$?
  CURRENT_DATE=$(ssh -n ${SSHUSER}@${HOST} "date --utc +%s")
else
  PRIMARYOUTPUT=$(kinit -t ${KEYTAB_NAME} -k ${KEYTAB_PRINCIPLE_UID}/${KEYTAB_PRINCIPLE_HOST} && ldapsearch -b ${SELECTED_DN} ${GROUP_FILTER_STRING_DN} -Y GSSAPI uid krbPasswordExpiration mail -LLL 2>&1)
  PRIMARYRETVAL=$?
  CURRENT_DATE=$(date --utc +%s)
fi

# Calculate the number of seconds until Expiry required to not be a warning
WARNING_DAYS_IN_SECONDS=$(expr 86400 \* $WARNLEVEL)
if [[ "$PRIMARYRETVAL" != "0" ]]; then
   echo "[UNKNOWN] ldapsearch is failing"
   exit 3;
fi

PRIMARYOUTPUT_CLEAN=$(echo "$PRIMARYOUTPUT" | grep -v ^SASL | grep -v "^dn: " | sed -e '/^$/d' -e ':a;N;$!ba;s/\n/,/g' -e 's/,,/,/g' -e 's/,uid:/\nuid:/g' -e 's/,/, /g' -e 's/, $//' | sed -e 's/^uid: \([^,]\+\), mail:/uid: \1, krbPasswordExpiration: 20991231235959Z, mail:/' | sed -e 's/\([0-9]\+Z\)$/\1, mail: admin@example.com/' | sed -e 's/^uid: //' -e 's/ krbPasswordExpiration://' -e 's/ mail://' | awk '{ OFS = ","; ORS = "\n"} {print $1 $2 $3}' | sed 's/,/ /g')
# Check if PRIMARYOUTPUT is blank - if so, immediately drop out as OK

#echo "$PRIMARYOUTPUT_CLEAN"

## Example PRIMARYOUTPUT_CLEAN
# admin,20200406053447Z,admins@ipa.example.com
# username1,20200406031558Z,username1@ipa.example.com
# username2,20200222152202Z,username2@ipa.exampl.com

COUNT=0
WARNINGCOUNT=0
CRITICALCOUNT=0
OKCOUNT=0
PRETTYPRINT=''
while read -r uid expiry email ; do

   

    # Convert expirt to second since the epoch
    datestamp_convert=$(echo $expiry | sed 's/\([0-9][0-9][0-9][0-9]\)\([0-9][0-9]\)\([0-9][0-9]\)\([0-9][0-9]\)\([0-9][0-9]\)\([0-9][0-9]\)Z/\1\/\2\/\3 \4:\5:\6Z/')
    expiry_epoch=$(date --date="$datestamp_convert" +"%s")

    # Difference between Today's datetime and the expiry
    DIFF=$(expr $expiry_epoch - $CURRENT_DATE)
    DAYS_LEFT=$(expr $DIFF / 86400)
    
    # Check Critical State first
    if [[ "$DAYS_LEFT" -le "0" ]]; then
       let "CRITICALCOUNT++"
       PRETTYPRINTCRIT="${PRETTYPRINTCRIT}Account ${uid} expires in ${DAYS_LEFT} days;"$'\n'
       PRETTYPRINT="${PRETTYPRINT}Account ${uid} expires in ${DAYS_LEFT} days;"$'\n'
    # Check Critical State first
    elif [[ "$DAYS_LEFT" -le "$WARNLEVEL" ]]; then
       let "WARNINGCOUNT++"
       PRETTYPRINTWARN="${PRETTYPRINTWARN}Account ${uid} expires in ${DAYS_LEFT} days"$'\n'
       PRETTYPRINT="${PRETTYPRINT}Account ${uid} expires in ${DAYS_LEFT} days;"$'\n'
    else
       let "OKCOUNT++"
       PRETTYPRINTOK="${PRETTYPRINTOK}Account ${uid} expires in ${DAYS_LEFT} days"$'\n'
       PRETTYPRINT="${PRETTYPRINT}Account ${uid} expires in ${DAYS_LEFT} days;"$'\n'
    ### OUTPUT
    fi
    let "COUNT++"
done <<< "$PRIMARYOUTPUT_CLEAN"


#
#echo "$CRITICALCOUNT"
#echo "$WARNINGCOUNT"
#echo "$OKCOUNT"
#echo "$COUNT"

## Make sure you reset the IFS or else the next read will fail to separate the variables
IFS=$IFS_BAK
PRETTYPRINTCRIT=$(echo "$PRETTYPRINTCRIT" | sed 'N;$s/\n//') # remove the final newline on the output so we don't get extra entries in future templates
PRETTYPRINTWARN=$(echo "$PRETTYPRINTWARN" | sed 'N;$s/\n//') # remove the final newline on the output so we don't get extra entries in future templates
PRETTYPRINTOK=$(echo "$PRETTYPRINTOK" | sed 'N;$s/\n//') # remove the final newline on the output so we don't get extra entries in future templates
PRETTYPRINT=$(echo "$PRETTYPRINT" | sed 'N;$s/\n//') # remove the final newline on the output so we don't get extra entries in future templates


sleep 1;
### Check each condition and increment the Relevant Critical and warn conditions

sleep 1;

# Test each condition and return the appropriate output.

# If Crit count is > 0, run critical output

if [[ "$CRITICALCOUNT" -gt "0" ]]
then
  if [[ "$PASSIVE_CHECK" -eq "0" ]]
  then
    curl -X POST -H 'Accept: application/json' --cacert $PASSIVE_CA_CERT --cert $PASSIVE_USER_CERT_CERT --key $PASSIVE_USER_CERT_KEY "${PASSIVE_API_URL}/v1/actions/process-check-result" -d "{ \"type\": \"Service\", \"filter\": \"host.name==\\\"$PASSIVE_HOST\\\" && service.name==\\\"$PASSIVE_SVC\\\"\", \"exit_status\": 2, \"plugin_output\": \"[CRITICAL] Some accounts have already expired\\n$(echo "$PRETTYPRINTCRIT" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\\\n/g')\\n$(echo "$PRETTYPRINTWARN" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\\\n/g')\", \"performance_data\": [ \"expired=$CRITICALCOUNT\", \"near_expired=$WARNINGCOUNT\", \"non_expired=$OKCOUNT\" ], \"check_source\": \"$HOSTNAME\"}"
  exit 0;
  else
    echo -e "[CRITICAL] Some accounts have already expired; | expired=$CRITICALCOUNT near_expired=$WARNINGCOUNT non_expired=$OKCOUNT\n${PRETTYPRINTCRIT}\n${PRETTYPRINTWARN}\n"
    exit 2;
  fi

# If Warn count is > 0, 

elif [[ "$WARNINGCOUNT" -gt "0" ]]
then
  if [[ "$PASSIVE_CHECK" -eq "0" ]]
  then
    curl -X POST -H 'Accept: application/json' --cacert $PASSIVE_CA_CERT --cert $PASSIVE_USER_CERT_CERT --key $PASSIVE_USER_CERT_KEY "${PASSIVE_API_URL}/v1/actions/process-check-result" -d "{ \"type\": \"Service\", \"filter\": \"host.name==\\\"$PASSIVE_HOST\\\" && service.name==\\\"$PASSIVE_SVC\\\"\", \"exit_status\": 1, \"plugin_output\": \"[WARNING] Accounts are below ${WARNLEVEL} Days to expiry\\n$(echo "$PRETTYPRINTWARN" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\\\n/g')\", \"performance_data\": [ \"expired=$CRITICALCOUNT\", \"near_expired=$WARNINGCOUNT\", \"non_expired=$OKCOUNT\" ], \"check_source\": \"$HOSTNAME\"}"
  exit 0;
  else
    echo -e "[WARNING] Accounts are below ${WARNLEVEL} Days to expiry; | expired=$CRITICALCOUNT near_expired=$WARNINGCOUNT non_expired=$OKCOUNT\n${PRETTYPRINTWARN}\n"
    exit 1;
  fi

# else Return OK;

else
  if [[ "$PASSIVE_CHECK" -eq "0" ]]
  then
    curl -X POST -H 'Accept: application/json' --cacert $PASSIVE_CA_CERT --cert $PASSIVE_USER_CERT_CERT --key $PASSIVE_USER_CERT_KEY "${PASSIVE_API_URL}/v1/actions/process-check-result" -d "{ \"type\": \"Service\", \"filter\": \"host.name==\\\"$PASSIVE_HOST\\\" && service.name==\\\"$PASSIVE_SVC\\\"\", \"exit_status\": 0, \"plugin_output\": \"[OK] There are no expired accounts\\n$(echo "$PRETTYPRINTOK" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\\\n/g')\", \"performance_data\": [ \"expired=$CRITICALCOUNT\", \"near_expired=$WARNINGCOUNT\", \"non_expired=$OKCOUNT\" ], \"check_source\": \"$HOSTNAME\"}"
  exit 0;
  else
    echo -e "[OK] There are no expired accounts;| expired=$CRITICALCOUNT near_expired=$WARNINGCOUNT non_expired=$OKCOUNT\n${PRETTYPRINT}\n"
    exit 0;
  fi
fi
