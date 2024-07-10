#! /usr/bin/python3

"""
description       :This monitor checks that status.kopf.progress exists and is not empty for each ResourceHandle
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import kubernetes
from pathlib import Path


parser = argparse.ArgumentParser(description='Monitor for Poolboy ResourceHandle data-integrity ')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api:4321"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the k8s secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-c', '--cacert', help='file path containing CA Cert for API', required=True, type=str, dest='cacert')
parser.add_argument('-d', '--deeplink', help='where to link the output', required=False, type=str, dest='deeplink', default="https://my.babylonui.example.com/admin/resourcehandles/")
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

# Prepare validation variables
resourcehandles_in_error = []
recovered = []
resourcehandles = custom_objects_api.list_cluster_custom_object('poolboy.gpte.redhat.com', 'v1', 'resourcehandles')['items']

# Run validation loop
for resourcehandle in resourcehandles:
    try:
        type(resourcehandle["status"]["kopf"]["progress"])
    except Exception:
        # Nothing found, so skip this item
        pass
    else:
        if resourcehandle["status"]["kopf"]["progress"]:
            resourcehandles_in_error.append(resourcehandle)
        else:
            recovered.append(resourcehandle)

# Nagios/Icinga output
if len(resourcehandles_in_error) == 0:
    exitstring = "[OK] No Resource Handles in Error found; | resourcehandles={};;;;; errorresourcehandles={};;;;; recovered={};;;;; ".format(
        len(resourcehandles), len(resourcehandles_in_error), len(recovered))
    print(exitstring)
    exit(0)
else:
    exitstring = "[WARNING] {err} Resource Handles in Error;| resourcehandles={total};;;;; errorresourcehandles={err};;;;; ecovered={re};;;;; ".format(
        re=len(recovered), total=len(resourcehandles), err=len(resourcehandles_in_error))
    print(exitstring)
    for handle in resourcehandles_in_error:
        url = "{}{}".format(args.deeplink, handle["metadata"]["name"])
        urlhandle = "<a target=\"_blank\" href=\"{}\">{}</a>".format(url, handle["metadata"]["name"])
        print(urlhandle, "<br>")
    exit(1)
