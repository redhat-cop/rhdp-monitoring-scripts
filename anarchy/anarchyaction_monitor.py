#! /usr/bin/python3

"""
description       :Checks Anarchy Actions for bad states so operations can investigate and resolve
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import kubernetes
import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description='Monitor for Anarchy Action data-integrity ')
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
anarchyactions = custom_objects_api.list_cluster_custom_object('anarchy.gpte.redhat.com', 'v1', 'anarchyactions')['items']

anarchyactions_in_error = {}

for anarchyaction in anarchyactions:
    d1 = datetime.datetime.strptime(anarchyaction["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    now = datetime.datetime.utcnow()
    timedelta = now - d1
    seconds_since_creation = int(timedelta.total_seconds())
    ##
    # Set error conditions
    ##
    kopfProgressExists = False
    subjectRefNotExists = False
    runScheduledError = False
    runRefMissing = False
    errorfound = False
    ###
    ###
    # print(anarchyaction["metadata"]["name"])
    try:
        anarchyaction["status"]["kopf"]["progress"]
    except Exception:
        # Nothing found, so skip this item
        pass
    else:
        kopfProgressExists = True
        errorfound = True
    #
    try:
        anarchyaction["spec"]["subjectRef"]
    except Exception:
        subjectRefNotExists = True
        errorfound = True
    else:
        pass
    ###
    # BLOCK for finished timestamps
    ###
    try:
        anarchyaction["status"]["finishedTimestamp"]
    except Exception:
        try:
            anarchyaction["status"]["runScheduled"]
        except Exception:
            try:
                anarchyaction["status"]["state"]
            except Exception:
                runScheduledError = True
                errorfound = True
            else:
                if anarchyaction["status"]["state"] != "successful":
                    runScheduledError = True
                    errorfound = True
        else:
            d2 = datetime.datetime.strptime(anarchyaction["status"]["runScheduled"], "%Y-%m-%dT%H:%M:%SZ")
            timedelta2 = now - d2
            seconds_since_runsched = int(timedelta2.total_seconds())
            if seconds_since_runsched < 0:  # runScheduled is in the future in this case
                pass
            else:  # runScheduled is either now or in past
                if seconds_since_runsched > 1800:  # if it's been more than 30 minutes, then we have an issue with this one not having a finishedTimestamp
                    runScheduledError = True
                    errorfound = True
    else:  # If there is a finishedTimestamp, then we're good
        pass
    ###
    # JAII - runRef model still not well understood - appears to be broken as many items do not have it but are actually in good state
    #         due to this, disabling current check
    # try:
    #  anarchyaction["status"]["runRef"]
    # except:
    #  if seconds_since_creation > 500:
    #    runRefMissing = True
    #    errorfound = True
    # else:
    #  pass
    ###
    # #
    ###
    if errorfound is True:
        anarchyactions_in_error[anarchyaction["metadata"]["name"]] = ""
        if kopfProgressExists is True:
            anarchyactions_in_error[anarchyaction["metadata"]["name"]] += "kopfProgressExists,"
        if subjectRefNotExists is True:
            anarchyactions_in_error[anarchyaction["metadata"]["name"]] += "subjectRefNotExists,"
        if runScheduledError is True:
            anarchyactions_in_error[anarchyaction["metadata"]["name"]] += "runScheduledError,"
        if runRefMissing is True:
            anarchyactions_in_error[anarchyaction["metadata"]["name"]] += "runRefMissing,"

anarchyaction_count = len(anarchyactions)
anarchyaction_errorcount = len(anarchyactions_in_error)

if anarchyaction_errorcount == 0:
    exitstring = "[OK] No Anarchy Action in Error found; | countactions=" + str(anarchyaction_count) + ";;;;; erroractions=" + str(anarchyaction_errorcount) + ";;;;;"
    print(exitstring)
    exit(0)
else:
    exitstring = "[WARNING] " + str(anarchyaction_errorcount) + " Anarchy Action in Error found; | countactions=" + str(anarchyaction_count) + ";;;;; erroractions=" + str(anarchyaction_errorcount) + ";;;;;"
    for action in anarchyactions_in_error:
        exitstring = exitstring + "\n" + str(action) + ": " + str(anarchyactions_in_error[action])
    print(exitstring)
    exit(1)
