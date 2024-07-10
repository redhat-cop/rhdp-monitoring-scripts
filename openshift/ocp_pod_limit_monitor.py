#! /usr/bin/python3

# Author: jappleii@redhat.com - John Apple II
# Description: Checks to see if any pods are exceeding their assigned limits
# License: Apache License v2
# Output: Nagios/Icinga2 format
###

import argparse
import kubernetes
import re
from pathlib import Path

pod_restarts_before_warning = 200

# Pre-compile our unit-splitter for OCP
# This should match "1.1Gi", "1K", or "1000343.343ABiC",
# but not "1.Gi" and not "1,000Gi"
# We will catch "1000343.343ABiC" in the functions
unit_split_re = re.compile('^(\d+(?:\.\d+)?)([iA-Z]+)$')


# Functions required for this program


def convert_ocp_container_memory_units_to_bytes(memory_string):
    # Convert to a string, and then validate that this has numeric and alpha chars for the split
    my_return_value = 0
    unit_string = str(memory_string)
    #
    #
    # Note, type Int, conversion is always 1 until changed, as 1 Byte = 1 Byte
    # For the value, we're assuming the conversion of 1 Byte into the value
    # (So 1 MegaByte (MB) = 1,000,000 Bytes, and 1 MebiByte (MiB) = 1,048,576)
    # so the my_conversion_ratio would equal 1000000 or 1048567, respectively.
    my_conversion_ratio = 1
    #
    # If the string has is not just a number, but has an alpha (e.g. attached units)
    # NOTE: the walrus operator ':=" was brought in Py3.8, RHEL7/8 default to Py3.6
    # if my_re_result := unit_split_re.match(unit_string)
    #   instead we have to split it between lines
    my_re_result = unit_split_re.match(unit_string)
    if my_re_result:
        my_unit_tuple = my_re_result.groups()
        # In these, we're taking the suffix of the unit and converting it
        if my_unit_tuple[1] == "Ki":
            my_conversion_ratio = 1024
        elif my_unit_tuple[1] == "K":
            my_conversion_ratio = 1000
        elif my_unit_tuple[1] == "Mi":
            my_conversion_ratio = 1048576
        elif my_unit_tuple[1] == "M":
            my_conversion_ratio = 1000000
        elif my_unit_tuple[1] == "Gi":
            my_conversion_ratio = 1073741824
        elif my_unit_tuple[1] == "G":
            my_conversion_ratio = 1000000000
        elif my_unit_tuple[1] == "Ti":
            my_conversion_ratio = 1099511627776
        elif my_unit_tuple[1] == "T":
            my_conversion_ratio = 1000000000000
        else:
            print(f'WE HAVE A UNIT SUFFIX WE DO NOT UNDERSTAND: {my_unit_tuple[1]}')
        my_return_value = float(my_unit_tuple[0]) * float(my_conversion_ratio)
        #
        #
        # This is just an integer, assume it's already KiB
    else:
        my_return_value = int(memory_string)
    return(int(my_return_value))


def convert_ocp_container_cpu_units_to_milli(cpu_string):
    # Convert to a string, and then validate that this has numeric and alpha chars for the split
    my_return_value = 0
    unit_string = str(cpu_string)
    #
    #
    # Note, type Int, millis are in 1000th of a CPU unit
    # In this function, we can hardcode this ratio for
    # whole units of CPU
    my_conversion_ratio = 1000
    #
    # If the string has is not just a number, but has an "m" at the end for "milli"
    if unit_string[-1] == "m":
        return(int(unit_string[:-1]))
    else:
        value = int(unit_string) * my_conversion_ratio
        return(int(value))


parser = argparse.ArgumentParser(description='Monitor for OCP/K8s pod limits ')
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

# Create list of all pods in the cluster
# Create list of all Pod Metrics in the cluster
pod_list = v1.list_namespaced_pod("").to_dict()["items"]

pod_metrics = custom_objects_api.list_cluster_custom_object('metrics.k8s.io', 'v1beta1', 'pods')['items']

# Prep the pod_usage data-structure
# del(pod_usage)
pod_usage = {}

# Create the pod and then container blanks for each entity in the cluster.
for item in pod_list:
    pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]] = {}
    #pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]]["POD"] = {"usage": {"cpu": None, "mem": None}, "limits": {"cpu": None, "mem": None}, "requests": {"cpu": None, "mem": None}, "restarts": 0}
    # Iterate through the spec_containers and populate the counts
    for container in item["spec"]["containers"]:
        pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]] = {"usage": {"cpu": None, "mem": None}, "limits": {"cpu": None, "mem": None}, "requests": {"cpu": None, "mem": None}, "restarts": 0}
        # Now, we iterate through each container, checking the limit and requests for both cpu and mem (4x try blocks) to populate the entry correctly
        try:
            useless = container["resources"]["limits"]["cpu"]
        except Exception:
            pass
        else:
            pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]]["limits"]["cpu"] = convert_ocp_container_cpu_units_to_milli(container["resources"]["limits"]["cpu"])
        ##
        try:
            useless = container["resources"]["limits"]["memory"]
        except Exception:
            pass
        else:
            pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]]["limits"]["mem"] = convert_ocp_container_memory_units_to_bytes(container["resources"]["limits"]["memory"])
        ##
        try:
            useless = container["resources"]["requests"]["cpu"]
        except Exception:
            pass
        else:
            pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]]["requests"]["cpu"] = convert_ocp_container_cpu_units_to_milli(container["resources"]["requests"]["cpu"])
        ##
        try:
            useless = container["resources"]["requests"]["memory"]
        except Exception:
            pass
        else:
            pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]]["requests"]["mem"] = convert_ocp_container_memory_units_to_bytes(container["resources"]["requests"]["memory"])
    # Now, pull the restart count of the Pod for some *very* basic error checking
    try:
        useless = item["status"]["container_statuses"][0]
    except Exception:
        pass
    else:
        for container_status in item["status"]["container_statuses"]:
            pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container_status["name"]]["restarts"] = container_status["restart_count"]

# Pod_list is no longer used - free the memory.
del(pod_list)

### Add in current usage metrics for each container (and the generic "POD" entry as provided by the metrics API)
for item in pod_metrics:
    for container in item["containers"]:
        if container["name"] != "POD":
            # Now, test that the container in metrics actually exists (because we've had issues 
            # where the metrics API sees a container which the pod API doesn't apparently know about.)
            try:
                useless = pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]]
            except Exception:
                pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]] = {"usage": {"cpu": None, "mem": None}, "limits": {"cpu": None, "mem": None}, "requests": {"cpu": None, "mem": None}, "restarts": 0}
            # Now, cycle through and update the cpu and mem usage for each container
            pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]]["usage"]["cpu"] = convert_ocp_container_cpu_units_to_milli(container["usage"]["cpu"])
            pod_usage[item["metadata"]["namespace"] + ":" + item["metadata"]["name"]][container["name"]]["usage"]["mem"] = convert_ocp_container_memory_units_to_bytes(container["usage"]["memory"])

# Pod_metrics is no longer required - free the memory.
del(pod_metrics)
#
# Data structure is
# pod_restarts_before_warning
monitor_output = {}
for pod in pod_usage:
    for container in pod_usage[pod]:
        errorrestarts = False
        errorcpu = False
        errormem = False
        if pod_usage[pod][container]["restarts"] is not None:
            if pod_usage[pod][container]["restarts"] >= pod_restarts_before_warning:
                errorrestarts = True
        if pod_usage[pod][container]["usage"]["cpu"] is not None and pod_usage[pod][container]["limits"]["cpu"] is not None:
            if pod_usage[pod][container]["usage"]["cpu"] > pod_usage[pod][container]["limits"]["cpu"]:
                errorcpu = True
        if pod_usage[pod][container]["usage"]["mem"] is not None and pod_usage[pod][container]["limits"]["mem"] is not None:
            if pod_usage[pod][container]["usage"]["mem"] > pod_usage[pod][container]["limits"]["mem"]:    
                errormem = True
        if errorrestarts or errorcpu or errormem:
            monitor_output[pod] = {}
            monitor_output[pod][container] = {}
            if errorrestarts:
                monitor_output[pod][container]["restarts"] = f'Restarts at {pod_usage[pod][container]["restarts"]}'
            if errorcpu:
                monitor_output[pod][container]["cpu"] = f'CPU milli limit:{pod_usage[pod][container]["limits"]["cpu"]} usage:{pod_usage[pod][container]["usage"]["cpu"]}'
            if errormem:
                monitor_output[pod][container]["mem"] = f'RAM bytes limit:{pod_usage[pod][container]["limits"]["mem"]} usage:{pod_usage[pod][container]["usage"]["mem"]}'


if len(monitor_output) == 0:
    print("[OK] Pod resources show no errors;")
    exit(0)
else:
    print("[WARNING] Pods with resource concerns found;")
    for pod in monitor_output:
        for container in monitor_output[pod]:
            print(f"{pod}::{container}:")
            for message in monitor_output[pod][container]:
                print(f"\t{monitor_output[pod][container][message]}")
    exit(1)

