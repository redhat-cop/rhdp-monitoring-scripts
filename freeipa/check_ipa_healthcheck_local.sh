#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Executes the IPA healthcheck command against the local IP and sends the output to an Icinga server using curl
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

# Execution examples
# Passive Check (curl)
# Passive Check (curl)
# check_ipa_account_expiry.sh -l "username" -d "cn=users,cn=accounts,dc=ipa,dc=example,dc=com" -F "(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)" -i /home/icinga/icinga-ipa_infra.crt -j /home/icinga/icinga-ipa_infra.key -c /home/icinga/ca.crt -a https://my.icinga.example.com:5665 -h host.ipa.example.com -x check_idm_user_expiry_admin -p 0
# Active Check
# check_ipa_account_expiry.sh -l "username" -d "cn=users,cn=accounts,dc=ipa,dc=example,dc=com" -F "(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)"


#echo "$@" > /tmp/commandargs
# Defaults
#HOME_PATH="/home/icinga"
KEYTAB_NAME=monitoring.keytab
KEYTAB_PRINCIPLE_UID="monitoring"
KEYTAB_PRINCIPLE_HOST=$(hostname)
HOSTNAME="$(hostname)"
PASSIVE_CHECK=1 # Default to active check

# Usage Function

function usage {
  ERR_MESSAGE="$@"
  echo "ERROR: $ERR_MESSAGE"
  echo "$(basename $0) usage: "
  echo "  [ -k keytab to be used to authenticate to LDAP ]"
  echo "  [ -K LDAP principle to use in the keytab ]"
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
      -k)
      KEYTAB_NAME="$2"
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
      ;;
  esac
  shift
done

# kinit -t /root/monitoring.keytab -k monitoring/host.ipa.example.com
# ldapwhoami -Y GSSAPI
# SASL/GSSAPI authentication started
# SASL username: monitoring/host.ipa.example.com@ipa.example.com@ipa.example.com
# SASL SSF: 256
# SASL data security layer installed.
# dn: krbprincipalname=monitoring/host.ipa.example.com@ipa.example.com,cn=services,cn=accounts,dc=ipa,dc=example,dc=com
# date --utc +%Y%m%d%H%M%SZ
# ldapsearch -b cn=users,cn=accounts,dc=ipa,dc=example,dc=com -Y GSSAPI - uid krbPasswordExpiration mail
# ldapsearch -b cn=users,cn=accounts,dc=ipa,dc=example,dc=com '(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)' -Y GSSAPI
# ldapsearch -b cn=users,cn=accounts,dc=ipa,dc=example,dc=com '(memberof=cn=admins,cn=groups,cn=accounts,dc=ipa,dc=example,dc=com)' -Y GSSAPI uid krbPasswordExpiration mail

# Set default levels if not set in the call
SSHUSER=${SSHUSER:-$USER}

# Validate SSH connectivity, and validate that anarchy has resources on this cluster
if [[ ${HOST} ]]; then
  ### VALIDATE SSH CONNECTIVITY, return 3 UNKNOWN if SSH connection fails
  ssh -n "${SSHUSER}"@"${HOST}" "ls" > /dev/null
  SSHRETVAL=$?
  if [[ "$SSHRETVAL" != "0" ]]; then
     echo "[UNKNOWN] ssh connection failing"
     exit 3;
  fi
fi

# Pull the primary input from the OC host - use SSH if the HOST variable is defined, else use a local command.
### OUTPUT should look like
if [[ ${HOST} ]]; then
  PRIMARYOUTPUT=$(ssh -n "${SSHUSER}"@"${HOST}" "kinit -t ${KEYTAB_NAME} -k ${KEYTAB_PRINCIPLE_UID}/${KEYTAB_PRINCIPLE_HOST} && ipa-healthcheck --failures-only --output-type json")
  PRIMARYRETVAL=$?
else
  PRIMARYOUTPUT=$(kinit -t "${KEYTAB_NAME}" -k "${KEYTAB_PRINCIPLE_UID}"/"${KEYTAB_PRINCIPLE_HOST}" && ipa-healthcheck --failures-only --output-type json)
  PRIMARYRETVAL=$?
fi

PRIMARYOUTPUT_CLEAN=$(echo "$PRIMARYOUTPUT" | jq '.[] | "\(.check) \(.result) \(.kw.msg)"' | sed 's/"//g') 
CRITICALCOUNT=$(echo "$PRIMARYOUTPUT_CLEAN" | grep -c "^")
if [[ "$PRIMARYRETVAL" -eq "0" ]]; then
  CRITICALCOUNT=0
fi

#echo "$PRIMARYOUTPUT_CLEAN"

## Example PRIMARYOUTPUT_CLEAN
# IPAsidgenpluginCheck ERROR null
# IPATrustAgentMemberCheck ERROR null
# IPATrustControllerPrincipalCheck ERROR null
# IPATrustControllerServiceCheck ERROR null
# IPATrustControllerConfCheck ERROR null
# IPATrustControllerGroupSIDCheck ERROR null
# IPATrustControllerAdminSIDCheck ERROR null
# IPATrustPackageCheck ERROR null
# MetaCheck ERROR null
# FileSystemSpaceCheck ERROR /var/lib/dirsrv/: free space percentage outside limits: 90% >= 20%

# Test each condition and return the appropriate output.

# If Crit count is > 0, run critical output

if [[ "$CRITICALCOUNT" -gt "0" ]]
then
  if [[ "$PASSIVE_CHECK" -eq "0" ]]
  then
    curl -X POST -H 'Accept: application/json' --cacert "$PASSIVE_CA_CERT" --cert "$PASSIVE_USER_CERT_CERT" --key "$PASSIVE_USER_CERT_KEY" "${PASSIVE_API_URL}/v1/actions/process-check-result" -d "{ \"type\": \"Service\", \"filter\": \"host.name==\\\"$PASSIVE_HOST\\\" && service.name==\\\"$PASSIVE_SVC\\\"\", \"exit_status\": 2, \"plugin_output\": \"[CRITICAL] IPA Healthcheck is failing\\n$(echo "$PRIMARYOUTPUT_CLEAN" | sed -E ':a;N;$!ba;s/\r{0,1}\n/\\\\n/g')\", \"performance_data\": [ \"errors=$CRITICALCOUNT\" ], \"check_source\": \"$HOSTNAME\"}"
  exit 0;
  else
    echo -e "[CRITICAL] IPA Healthcheck is failing; | errors=$CRITICALCOUNT \n$PRIMARYOUTPUT_CLEAN"
    exit 2;
  fi

# else Return OK;

else
  if [[ "$PASSIVE_CHECK" -eq "0" ]]
  then
    curl -X POST -H 'Accept: application/json' --cacert "$PASSIVE_CA_CERT" --cert "$PASSIVE_USER_CERT_CERT" --key "$PASSIVE_USER_CERT_KEY" "${PASSIVE_API_URL}/v1/actions/process-check-result" -d "{ \"type\": \"Service\", \"filter\": \"host.name==\\\"$PASSIVE_HOST\\\" && service.name==\\\"$PASSIVE_SVC\\\"\", \"exit_status\": 0, \"plugin_output\": \"[OK] IPA Healthcheck passed all checks\\n\", \"performance_data\": [ \"errors=$CRITICALCOUNT\" ], \"check_source\": \"$HOSTNAME\"}"
  exit 0;
  else
    echo -e "[OK] IPA Healthcheck passed all checks;| errors=$CRITICALCOUNT \n"
    exit 0;
  fi
fi
