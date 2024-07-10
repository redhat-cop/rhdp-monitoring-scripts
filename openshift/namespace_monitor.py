#! /usr/bin/python3

"""
description       :This monitor checks the number of namespaces in the cluster against the engineering limit setup in the monitor arguments, which is about 10k namespaces. YMMV, but we did our own load tests and this seems fairly accurate for a stable cluster
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import kubernetes
from pathlib import Path

# Set Limits for our checks
#
max_namespaces = 10000

parser = argparse.ArgumentParser(description='Monitor for count of OCP/K8s cluster namespaces against the engineering limit')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api:4321"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the k8s secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-c', '--cacert', help='file path containing CA Cert for API', required=True, type=str, dest='cacert')
parser.add_argument('-w', '--warning', help='number of namespaces in-use which constitutes warning status', required=True, type=int, dest='warningcount')
parser.add_argument('-r', '--critical', help='number of namespaces in-use which constitutes critical status', required=True, type=int, dest='criticalcount')
parser.add_argument('-m', '--max', help='engineering limit of the cluster - beyond this the cluster begins to fail', required=True, type=int, dest='maxcount')
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

# Pull all resources required
#
namespaces = v1.list_namespace().to_dict()["items"]
namespacecount = len(namespaces)

if namespacecount >= args.maxcount:
    exitstring = f"[CRITICAL FAILURE] maximum namespaces exceeded: at {namespacecount} with {args.maxcount} max; | namespaces={namespacecount};{args.warningcount};{args.criticalcount};0;{args.maxcount};"
    print(exitstring)
    exit(2)
elif namespacecount > args.criticalcount:
    exitstring = f"[CRITICAL] namespaces above critical level: at {namespacecount} with {args.criticalcount} critical; | namespaces={namespacecount};{args.warningcount};{args.criticalcount};0;{args.maxcount};"
    print(exitstring)
    exit(2)
elif namespacecount > args.warningcount:
    exitstring = f"[WARNING] namespaces above warning level: at {namespacecount} with {args.warningcount} warning; | namespaces={namespacecount};{args.warningcount};{args.criticalcount};0;{args.maxcount};"
    print(exitstring)
    exit(1)
else:
    exitstring = f"[OK] namespaces within normal range: {namespacecount} namespaces  | namespaces={namespacecount};{args.warningcount};{args.criticalcount};0;{args.maxcount};"
    print(exitstring)
    exit(0)
