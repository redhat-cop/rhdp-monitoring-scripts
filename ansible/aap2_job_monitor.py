#! /usr/bin/python3

"""
description       :This monitor is designed to count jobs in an AAP2 control plane and then monitor by their state
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import requests
from pathlib import Path

parser = argparse.ArgumentParser(description='Monitor for AAP2 Job status - using api/v2/jobs ')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api/v2/jobs"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-u', '--username', help='Username for the user for monitoring the AAP2 server', required=True, type=str, dest='username')
parser.add_argument('-p', '--pending-warning', help='count of pending jobs that constitutes warning', required=True, type=str, dest='level_warn_pending')
parser.add_argument('-q', '--pending-critical', help='count of pending jobs that constitutes critical', required=True, type=str, dest='level_crit_pending')
parser.add_argument('-r', '--running-warning', help='count of running jobs that constitutes warning', required=True, type=str, dest='level_warn_running')
parser.add_argument('-t', '--running-critical', help='count of running jobs that constitutes critical', required=True, type=str, dest='level_crit_running')
parser.add_argument('-w', '--waiting-warning', help='count of waiting jobs that constitutes warning', required=True, type=str, dest='level_warn_waiting')
parser.add_argument('-v', '--waiting-critical', help='count of waiting jobs that constitutes critical', required=True, type=str, dest='level_crit_waiting')
args = parser.parse_args()

api_password = Path(args.secret_path).read_text().strip()
valid_aap2_job_states = {"pending", "running", "waiting", "failed", "new", "successful"}
count = {}
# Stage count variables
for state in valid_aap2_job_states:
    response = requests.get('https://' + args.apiurl + '/api/v2/jobs/', params={'status': state, 'page_size': '1'}, auth=(args.username, api_password))
    count[state] = response.json()["count"]

# pprint(count)
# {'failed': 731,
#  'new': 0,
#  'pending': 0,
#  'running': 1,
#  'successful': 3058,
#  'waiting': 0}
#

###
# Check for warning and critical states and record
###
is_critical = False
is_warning = False

perfdata_string = "; | running={};;;;; new={};;;;; pending={};;;;; waiting={};;;;; successful={};;;;; failed={};;;;; ".format(count["running"], count["new"], count["pending"], count["waiting"], count["successful"], count["failed"])

if int(count["running"]) >= int(args.level_crit_running) or int(count["pending"]) >= int(args.level_crit_pending) or int(count["waiting"]) >= int(args.level_crit_waiting):
    is_critical = True
    is_warning = False
elif int(count["running"]) >= int(args.level_warn_running) or int(count["pending"]) >= int(args.level_warn_pending) or int(count["waiting"]) >= int(args.level_warn_waiting):
    is_critical = False
    is_warning = True
else:
    is_critical = False
    is_warning = False

###
# Provide the exit code
###
if is_critical is True:
    exitstring = "[CRITICAL] Ansible Controller jobs status is in critical state;"
    print(exitstring + perfdata_string)
    exit(2)
elif is_warning is True:
    exitstring = "[WARNING] Ansible Controller jobs status is in warning state;"
    print(exitstring + perfdata_string)
    exit(1)
else:
    exitstring = "[OK] Ansible Controller jobs status is ok;"
    print(exitstring + perfdata_string)
    exit(0)
