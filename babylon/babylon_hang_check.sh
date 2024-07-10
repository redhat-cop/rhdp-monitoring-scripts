#!/bin/bash

# Author: jappleii@redhat.com - John Apple II
# Description: Find anarchy runs stuck in pending to verify that the anarchy-runner is not hung on an error
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

function usage {
  echo "$(basename "$0") usage: "
  echo "    -h remote_host"
  echo "    -u remote_user"
  echo ""
  exit 1
}

while [[ $# -gt 1 ]]
do
    key="$1"
    case $key in
      -h)
      HOST="$2"
      shift
      ;;
      -u)
      USER="$2"
      shift
      ;;
      *)
      usage
      ;;
  esac
  shift
done

[ -n "${HOST}" ] && [ -n "${USER}" ] || usage


pending_runs_count="$(ssh "${USER}"@"${HOST}" -C "oc get anarchyrun -n anarchy-operator -l 'anarchy.gpte.redhat.com/runner==pending' | wc -l" 2>/dev/null)"

if [[ ${pending_runs_count} -gt 100 ]]
then
  echo "[CRITICAL] - ${pending_runs_count} pending runs are in the Babylon Anarchy queue" 
  exit 2
elif [[ ${pending_runs_count} -gt 50 ]]
then
  echo "[WARNING] - ${pending_runs_count} pending runs are in the Babylon Anarchy queue"
  exit 1
else
  echo "[OK] - ${pending_runs_count} pending runs in the Babylon Anarchy queue"
  exit 0
fi
