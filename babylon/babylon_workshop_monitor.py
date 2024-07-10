#! /usr/bin/python3

"""
description       :This monitor takes 2 limit numbers and a max number, counts the number of namespaces in an openshift cluster, warning if either limit is exceeded.
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import kubernetes
from pathlib import Path

# Create the base Datastructure for our monitor
# [{ username: {
#    project: projectname,
#    rolebindings: [rolebinding1, rolebinding2, ...],
#    id_groups: [id_group1, id_group2, ...],
#    emailgroup: emailgroupname
#    email: email@domain.tld,
#    isinerror: Boolean,
#    errorflags: ""
#  ,..
#  }}]

parser = argparse.ArgumentParser(description='Monitor for Babylon Workshop data-integrity ')
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


workshops_in_error = []
workshops = custom_objects_api.list_cluster_custom_object('babylon.gpte.redhat.com', 'v1', 'workshops')['items']

for workshop in workshops:
    try:
        type(workshop["status"]["kopf"]["progress"])
    except Exception:
        # Nothing found, so skip this item
        pass
    else:
        # This is only true if the kopf.progress dict has members, else it
        # evaluates false.
        if len(workshop["status"]["kopf"]["progress"]) > 0:
            workshops_in_error.append(workshop["metadata"]["namespace"] + ": " + workshop["metadata"]["name"])

errorcount = len(workshops_in_error)

if errorcount == 0:
    exitstring = "[OK] No Workshops in Error found; | workshops=" + str(len(workshops)) + ";;;;; errorworkshops=" + str(errorcount) + ";;;;; "
    print(exitstring)
    exit(0)
else:
    exitstring = "[WARNING] Workshops in Error;| workshops=" + str(len(workshops)) + ";;;;; errorworkshops=" + str(errorcount) + ";;;;; "
    for claim in workshops_in_error:
        exitstring = exitstring + "\n" + claim
    print(exitstring)
    exit(1)