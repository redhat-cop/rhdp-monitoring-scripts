#! /usr/bin/python3

"""
description       :Checks Anarchy Runs for bad states so operations can investigate and resolve
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""


import argparse
import urllib3
import kubernetes
import datetime
from pprint import pprint
from pathlib import Path

###
#   Constants
###
seconds_considered_not_too_long = 60

parser = argparse.ArgumentParser(description='Monitor for Anarchy Run data-integrity ')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api:4321"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the k8s secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-c', '--cacert', help='file path containing CA Cert for API', required=True, type=str, dest='cacert')
args = parser.parse_args()

# setup the client
apikey = Path(args.secret_path).read_text()
aConfig = kubernetes.client.Configuration()
aConfig.api_key = {"authorization": "Bearer " + apikey}
aConfig.host = args.apiurl
aConfig.ssl_ca_cert = args.cacert
aApiClient = kubernetes.client.ApiClient(aConfig)
# ocp_client = DynamicClient(aApiClient)
custom_objects_api = kubernetes.client.CustomObjectsApi(aApiClient)
v1 = kubernetes.client.CoreV1Api(aApiClient)
anarchyruns = custom_objects_api.list_cluster_custom_object('anarchy.gpte.redhat.com', 'v1', 'anarchyruns')['items']

anarchyruns_in_error = {}

for anarchyrun in anarchyruns:
    d1 = datetime.datetime.strptime(anarchyrun["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    now = datetime.datetime.utcnow()
    timedelta = now - d1
    seconds_since_creation = int(timedelta.total_seconds())
    FoundError = False
    entryKopf = False
    entryrunnerPod = False
    entryState = False
    #
    try:
        anarchyrun["status"]["kopf"]["progress"]
    except Exception:
        # Nothing found, so skip this item
        pass
    else:
        entryKopf = True
        FoundError = True
    #
    try:
        anarchyrun["status"]["runnerPod"]["name"]
    except Exception:
        if seconds_since_creation > (seconds_considered_not_too_long + 1800):  # Add 30 minutes at request of prutledge
            entryrunnerPod = True
            FoundError = True
    #
    try:
        anarchyrun["status"]["result"]["status"]
    except Exception:
        entryState = True
        FoundError = True
    else:
        try:
            anarchyrun["status"]["runnerPod"]
        except Exception:
            entryrunnerPod = True
            FoundError = True

    if FoundError is True:
        anarchyruns_in_error[anarchyrun["metadata"]["name"]] = ""
        if entryKopf:
            anarchyruns_in_error[anarchyrun["metadata"]["name"]] += "kopfprogressExists,"
        if entryrunnerPod:
            anarchyruns_in_error[anarchyrun["metadata"]["name"]] += "runnerPodMissing,"
        if entryState:
            anarchyruns_in_error[anarchyrun["metadata"]["name"]] += "stateNotSuccessful,"

anarchyrun_count = len(anarchyruns)
anarchyrun_errorcount = len(anarchyruns_in_error)

if anarchyrun_errorcount == 0:
    exitstring = "[OK] No Anarchy Runs in Error found; | countruns=" + str(anarchyrun_count) + ";;;;; errorruns=" + str(anarchyrun_errorcount) + ";;;;;"
    print(exitstring)
    exit(0)
else:
    exitstring = "[WARNING] " + str(anarchyrun_errorcount) + " Anarchy Runs in Error found; | countruns=" + str(anarchyrun_count) + ";;;;; errorruns=" + str(anarchyrun_errorcount) + ";;;;;"
    for run in anarchyruns_in_error:
        exitstring = exitstring + "\n" + str(run) + ": " + str(anarchyruns_in_error[run])
    print(exitstring)
    exit(1)
