#!/bin/bash

  # Author: yvarbev@redhat.com - Yordan Varbev
  # Description: Checks Ansible Tower hosts to confirm all hosts are running
  #              Output is in Nagios format
  # License: Apache License v2
  ###


function usage {
  echo "$(basename $0) usage: "
  echo "    -w warning_level"
  echo "    -c critical_level"
  echo "  [ -h remote_host ]"
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
      -w)
      WARN="$2"
      shift
      ;;
      -c)
      CRIT="$2"
      shift
      ;;
      *)
      usage
      ;;
  esac
  shift
done

[ ! -z ${WARN} ] && [ ! -z ${CRIT} ] || usage

function check_ansible_tower() {
    local count_running=$1
    local warn=$2
    local crit=$3
      if [ "$crit" -ge "$count_running" ]; then
        export chk_c=true
      elif [[ "$warn" -ge "$count_running" ]]; then
        export chk_w=true
      fi
}


function main() {

  if [[ ${HOST} ]]; then
    output=$(sudo ssh ${HOST} sudo supervisorctl status | awk '{ print $1 " " $2 }')
    count_running=$(sudo ssh ${HOST} sudo supervisorctl status | grep -c RUNNING)
    printr=$(sudo ssh ${HOST} sudo supervisorctl status | sed -e 's/RUNNING/1/' -e 's/STOPPED/0/' | awk -v w=${WARN} -v c=${CRIT} '{ print $1"="$2";"0";"0 }')
  else
    output=$(sudo supervisorctl status | awk '{ print $1 " " $2 }')
    count_running=$(sudo supervisorctl status | grep -c RUNNING)
    printr=$(sudo supervisorctl status | sed -e 's/RUNNING/1/' -e 's/STOPPED/0/' | awk -v w=${WARN} -v c=${CRIT} '{ print $1"="$2";"0";"0 }')
  fi

  check_ansible_tower "$count_running" ${WARN} ${CRIT}

  if [[ ${chk_c} ]]; then
    echo "[CRITICAL] only $CRIT tower procs running |" ${printr}
    exit 2
  elif [[ ${chk_w} ]]; then
    echo "[WARNING] only $WARN tower procs running  |" ${printr}
    exit 1
  else
    echo "[OK] all 7 tower procs running |" ${printr}
    exit 0
  fi

}

#Run
main

