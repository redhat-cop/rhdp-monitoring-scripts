#! /usr/bin/python3

"""
description       :This monitor checks that status.kopf.progress is undefined for each ResourceClaim
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import kubernetes
from pathlib import Path

parser = argparse.ArgumentParser(description='Monitor for Poolboy ResourceClaim data-integrity ')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api:4321"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the k8s secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-c', '--cacert', help='file path containing CA Cert for API', required=True, type=str, dest='cacert')
parser.add_argument('-d', '--deeplink', help='where to link the output', required=False, type=str, dest='deeplink', default="https://my.babylonui.example.com/services/")
args = parser.parse_args()

# setup the client
apikey = Path(args.secret_path).read_text()
aConfig = kubernetes.client.Configuration()
aConfig.api_key = {"authorization": "Bearer " + apikey}
aConfig.host = args.apiurl
aConfig.ssl_ca_cert = args.cacert
aApiClient = kubernetes.client.ApiClient(aConfig)
custom_objects_api = kubernetes.client.CustomObjectsApi(aApiClient)
v1 = kubernetes.client.CoreV1Api(aApiClient)

# Prepare our resourceclaim lists
resourceclaims_in_error = []
resourceclaims = custom_objects_api.list_cluster_custom_object('poolboy.gpte.redhat.com', 'v1', 'resourceclaims')['items']

# Run validation loop
for resourceclaim in resourceclaims:
    resourceclaim_in_error = 0
    resourceclaim_error_flags: list = []
    # Kopf progress exists
    try:
        type(resourceclaim["status"]["kopf"]["progress"])
    except Exception:
        # Nothing found, so skip this item
        pass
    else:
        if resourceclaim["status"]["kopf"]["progress"]:
            resourceclaim_in_error = 1
            resourceclaim_error_flags.append("kopfProgressExists")

    # Validation Errors are discovered here
    try:
        type(resourceclaim["status"]["resources"][0]["validationError"])
    except Exception:
        # Nothing found, so skip this item
        pass
    else:
        if resourceclaim["status"]["resources"][0]["validationError"]:
            resourceclaim_in_error = 1
            resourceclaim_error_flags.append("validationError")

    if resourceclaim_in_error:
        resourceclaim_string = resourceclaim["metadata"]["name"] + ":"
        for error in resourceclaim_error_flags:
            resourceclaim_string = "\t" + resourceclaim_string + " " + error
        resourceclaims_in_error.append(resourceclaim_string)

# Nagios/Icinga output based on errors
if len(resourceclaims_in_error) == 0:
    exitstring = "[OK] No Resource Claims in Error found; | resourceclaims={};;;;; errorresourceclaims={};;;;; ".format(
        len(resourceclaims), len(resourceclaims_in_error))
    print(exitstring)
    exit(0)
else:
    exitstring = "[WARNING] {} Resource Claims in Error;| resourceclaims={};;;;; errorresourceclaims={};;;;; ".format(
        len(resourceclaims_in_error), len(resourceclaims), len(resourceclaims_in_error))
    print(exitstring)
    for claim in resourceclaims_in_error:
        print(claim)
        exit(1)
