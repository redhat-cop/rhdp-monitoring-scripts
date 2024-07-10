#!/usr/bin/env python3

"""
description       :Checks the status of the Babylon Pools for any that are empty or are below the Warning or Critical limit
author            :jappleii@redhat.com (John Apple II)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import kubernetes
import logging
import argparse
import urllib3
from tabulate import tabulate
from pathlib import Path

urllib3.disable_warnings()

parser = argparse.ArgumentParser(description='Monitor for Babylon Pools - note ignores pools with max value of 0')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api:4321"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the k8s secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-c', '--cacert', help='file path containing CA Cert for API', required=True, type=str, dest='cacert')
parser.add_argument('-p', '--pattern', help='only use pools that match this pattern', required=False, type=str, dest='pool_pattern')
parser.add_argument('-i', '--ignorepattern', help='ignore any pools that match this pattern', required=False, type=str, dest='pool_ignore_pattern')
parser.add_argument('-f', '--format', help='output format for tabulate', required=False, type=str, dest='table_format', default='simple')
parser.add_argument('-w', '--warning', help='% number pool members that counts as a warning', required=False, type=int, dest='warning_percentage', default=50)
parser.add_argument('-r', '--critical', help='% number of pool members that counts as a critical', required=False, type=int, dest='critical_percentage', default=10)
parser.add_argument('-z', '--skipzero', help='skip printing pools with a min_desired of 0', required=False, type=bool, dest='skipzero', default=True)
args = parser.parse_args()

# setup the client
apikey = Path(args.secret_path).read_text()
aConfig = kubernetes.client.Configuration()
aConfig.api_key = {"authorization": "Bearer " + apikey}
aConfig.host = args.apiurl
aConfig.ssl_ca_cert = args.cacert
aApiClient = kubernetes.client.ApiClient(aConfig)
core_v1_api = kubernetes.client.CoreV1Api(aApiClient)
custom_objects_api = kubernetes.client.CustomObjectsApi(aApiClient)
logger = logging.getLogger()

response_pools = custom_objects_api.list_namespaced_custom_object(
    'poolboy.gpte.redhat.com',
    'v1',
    'poolboy',
    'resourcepools')

pools = response_pools['items']
output = [["POOL", "MIN", "AVAILABLE", "TAKEN", "TOTAL", "STATUS"]]
outputerror = [["POOL", "MIN", "AVAILABLE", "TAKEN", "TOTAL", "STATUS"]]
ttotal = 0
tavailable = 0
ttaken = 0

# setup warning and critical base flags
is_crit = 0
is_warn = 0

for pool in pools:
    if args.pool_pattern and args.pool_pattern not in pool['metadata']['name']:
        continue
    if args.pool_ignore_pattern and args.pool_ignore_pattern in pool['metadata']['name']:
        continue
    label = 'poolboy.gpte.redhat.com/resource-pool-name=' + pool['metadata']['name']
    handles_resp = custom_objects_api.list_namespaced_custom_object(
        'poolboy.gpte.redhat.com',
        'v1',
        'poolboy',
        'resourcehandles',
        label_selector=label)
    handles = handles_resp['items']
    min_available = pool['spec']['minAvailable']
    total = 0
    available = 0
    taken = 0
    for handle in handles:
        total = total + 1
        ttotal = ttotal + 1
        if 'resourceClaim' in handle['spec']:
            taken = taken + 1
            ttaken = ttaken + 1
            continue
        if 'resources' not in handle['spec']:
            continue
        totalresource = len(handle['spec']['resources'])
        resourcecompleted = 0
        for resource in handle['spec']['resources']:
            try:
                if resource['reference']['kind'] == 'AnarchySubject':
                    subject = custom_objects_api.get_namespaced_custom_object(
                        'anarchy.gpte.redhat.com', 'v1', resource['reference']['namespace'], 'anarchysubjects', resource['reference']['name'])
                    try:
                        if subject['spec']['vars']['desired_state'] == subject['spec']['vars']['current_state']:
                            if subject['spec']['vars']['healthy'] is True:
                                resourcecompleted = resourcecompleted + 1
                    except Exception:
                        pass
            except Exception:
                pass
        if resourcecompleted == len(handle['spec']['resources']):
            available = available + 1
            tavailable = tavailable + 1
    # Setup warning/critical threshold values per pool based on value of total poolsize, and test against available.
    if total == 0:
        my_warn_value = -1
        my_crit_value = -1
    else:
        my_warn_value = int(round(float((args.warning_percentage * min_available) / 100.0)))
        my_crit_value = int(round(float((args.critical_percentage * min_available) / 100.0)))
    # print(f"poolsize = {min_available}, warn = {my_warn_value}, crit = {my_crit_value}, available = {available}")
    # Test for critical and warning values in the output
    if args.skipzero:
        if min_available == 0:
            continue
    if available < my_crit_value:
        # print("Is crit")
        is_crit += 1
        outputerror.append([pool['metadata']['name'], str(min_available), str(available), str(taken), str(total), str("CRITICAL")])
    elif available < my_warn_value:
        # print("Is warn")
        is_warn += 1
        outputerror.append([pool['metadata']['name'], str(min_available), str(available), str(taken), str(total), str("WARNING")])
    else:
        # print("Is ok")
        output.append([pool['metadata']['name'], str(min_available), str(available), str(taken), str(total), str("---")])

if output:
    if is_crit > 0:
        print('[CRITICAL] Pools list (warning {}%, critical {}%): | in-Use={};;;0;{} available={};;;0;{}'.format(args.warning_percentage, args.critical_percentage, ttaken, ttotal, tavailable, ttotal))
        print(tabulate(outputerror, headers='firstrow', tablefmt=args.table_format))
        exit(2)
    elif is_warn > 0:
        print('[WARNING] Pools list (warning {}%, critical {}%): | in-Use={};;;0;{} available={};;;0;{}'.format(args.warning_percentage, args.critical_percentage, ttaken, ttotal, tavailable, ttotal))
        print(tabulate(outputerror, headers='firstrow', tablefmt=args.table_format))
        exit(1)
    else:
        print('[OK] Pools list (warning {}%, critical {}%): | in-Use={};;;0;{} available={};;;0;{}'.format(args.warning_percentage, args.critical_percentage, ttaken, ttotal, tavailable, ttotal))
        print(tabulate(output, headers='firstrow', tablefmt=args.table_format))
        exit(0)
else:
    print('[WARN] Could not get pool information')
    exit(1)
