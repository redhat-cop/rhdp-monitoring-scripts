#! /usr/bin/python3

"""
description       :This monitor checks Babylon Namespaces for data integrity errors
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import kubernetes
from pathlib import Path

# Set Limits for our checks
max_namespaces = 10000

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

parser = argparse.ArgumentParser(description='Monitor for Babylon Namespace data-integrity')
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

# Pull all resources required
#
namespaces = v1.list_namespace(label_selector='app.kubernetes.io/name=anarchy').to_dict()["items"]


# Setup primary check namespace list
pods_state = {}

for name in namespaces:
    my_name = name["metadata"]["name"]
    if my_name == "anarchy":
        continue
    pod_list = v1.list_namespaced_pod(my_name).to_dict()["items"]
    pods_state[my_name] = {}
    for pod in pod_list:
        pods_state[my_name][pod["metadata"]["name"]] = pod["status"]["phase"]


# Prepare for error search
errorfound = False
monitor_output = {}

# Begin searching for errors
for namespace in pods_state:
    monitor_output[namespace] = {}
    monitor_output[namespace]["runner"] = False
    monitor_output[namespace]["runner_default_pods"] = 0
    monitor_output[namespace]["other_exception"] = False
    if len(pods_state[namespace]) < 1:
        monitor_output[namespace]["other_exception"] = True
        errorfound = True
    for pod in pods_state[namespace]:
        if pod.startswith('anarchy-runner-default'):
            if pods_state[namespace][pod] == "Running":
                monitor_output[namespace]["runner_default_pods"] += 1
            else:
                errorfound = True
        elif pod.startswith('anarchy-'):
            if pods_state[namespace][pod] == "Running":
                monitor_output[namespace]["runner"] = True
            else:
                errorfound = True
        else:
            monitor_output[namespace]["other_exception"] = True
            errorfound = True


if errorfound is False:
    exitstring = "[OK] Anarchy Namespaces are good;"
    print(exitstring)
    exit(0)
else:
    exitstring = "[WARNING] Anarchy Namespaces in Error found;"
    for namespace in monitor_output:
        errorstring = ""
        if monitor_output[namespace]["runner_default_pods"] < 1:
            errorstring += "NoRunnerDefaultPods,"
        if monitor_output[namespace]["runner"] is False:
            errorstring += "NoRunnerPod,"
        if monitor_output[namespace]["other_exception"] is True:
            errorstring += "OtherException,"
        if errorstring == "":
            pass
        else:
            exitstring = exitstring + "\n" + str(namespace) + ": " + str(errorstring)
    print(exitstring)
    exit(1)
