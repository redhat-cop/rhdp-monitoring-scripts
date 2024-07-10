#! /usr/bin/python3

"""
description       :This monitor checks an OCP Virt enabled cluster for Virtual Machines, PVC's, and PV's in error or aged beyond a particular date (14 days ago)
author            :jappleii@redhat.com (John Apple II) - Developed with the help of ChatGPT 4o
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import urllib3
import argparse
import kubernetes
from pathlib import Path
from datetime import datetime, timezone

# Setup the date object for now for future checks
time_now = datetime.now(timezone.utc)

# Suppress only the InsecureRequestWarning from urllib3 since python doesn't like OCP/K8s' self-signed cluster certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Initialize argument parser
parser = argparse.ArgumentParser(description='Monitor for OCP Virt and Volumes')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api:4321"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the k8s secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-c', '--cacert', help='file path containing CA Cert for API', required=True, type=str, dest='cacert')
args = parser.parse_args()

# Function to fetch and store the SSL certificate
# import ssl
# import socket
# def fetch_and_store_cert(apiurl, cacert_path):
#    hostname = apiurl.split("//")[-1].split("/")[0].split(":")[0]
#    port = 6443  # Default HTTPS port
#    context = ssl.create_default_context()
#    conn = context.wrap_socket(socket.socket(socket.AF_INET), server_hostname=hostname)
#    conn.connect((hostname, port))
#    cert = conn.getpeercert(True)
#    pem_cert = ssl.DER_cert_to_PEM_cert(cert)
#    with open(cacert_path, 'w') as cert_file:
#        cert_file.write(pem_cert)

# Fetch and store the certificate
# fetch_and_store_cert(args.apiurl, args.caceron.total_seconds(t)

# Setup the Kubernetes client
apikey = Path(args.secret_path).read_text().strip()
aConfig = kubernetes.client.Configuration()
aConfig.api_key = {"authorization": "Bearer " + apikey}
aConfig.host = args.apiurl
aConfig.ssl_ca_cert = args.cacert
aConfig.verify_ssl = False
aApiClient = kubernetes.client.ApiClient(aConfig)
custom_objects_api = kubernetes.client.CustomObjectsApi(aApiClient)
v1 = kubernetes.client.CoreV1Api(aApiClient)


# Pull and return the list of Namespaces in the cluster
def get_namespaces():
    namespaces = v1.list_namespace().items
    return [ns.metadata.name for ns in namespaces]


# Pull and return the list of Virtual machines in a specific namespace
# Return the VM Objects
def get_virtual_machines(namespace):
    group = 'kubevirt.io'
    version = 'v1'
    plural = 'virtualmachines'
    vms = custom_objects_api.list_namespaced_custom_object(group, version, namespace, plural)['items']
    return vms


# Pull all PVCs in a namespace
# Return the PVC objects
def get_pvcs(namespace):
    pvcs = v1.list_namespaced_persistent_volume_claim(namespace).items
    return pvcs


# Pull all PVs in the cluster
# Return the PV objects
def get_pvs():
    pvs = v1.list_persistent_volume().items
    return pvs


# Get a VM Object, obtain it's status, the last date for a change known as datetime, and age as timedelta from now
# Return a string, datetime object, and timedelta
def check_vm_status(vm):
    status = vm.get('status', {}).get('printableStatus', 'Unknown')
    vm_time = vm.get('status', {}).get('conditions', [{}])[-1].get('lastTransitionTime')
    if vm_time is None:
        vm_time = vm.get('metadata', {}).get('creationTimestamp')
    if vm_time.endswith('Z'):
        vm_time = vm_time.replace('Z', '+0000')
    last_transition_time = datetime.strptime(vm_time, '%Y-%m-%dT%H:%M:%S%z')
    age = time_now - last_transition_time
    return status, last_transition_time, age


# Get a PVC Object, obtain it's status, the last date for a change known as datetime, and age as timedelta from now
# Return a string, datetime object, and timedelta
def check_pvc_status(pvc):
    status = pvc.status.phase
    last_transition_time = pvc.metadata.creation_timestamp
    age = time_now - last_transition_time
    return status, last_transition_time, age


# Get a PV Object, obtain it's status, the last date for a change known as datetime, and age as timedelta from now
# Return a string, datetime object, and timedelta
def check_pv_status(pv):
    status = pv.status.phase
    last_transition_time = pv.metadata.creation_timestamp
    age = time_now - last_transition_time
    return status, last_transition_time, age


# Format the duration as a statement "DDDHHMM ago"
# Returns the string
def format_age(duration):
    seconds = duration.total_seconds()
    days = int(seconds // 86400)
    hours = int(seconds % 86400 // 3600)
    minutes = int((seconds % 3600) // 60)
    return f"{days}d_{hours}h_{minutes}m ago"


def main():
    namespaces = get_namespaces()
    pvcs = {ns: get_pvcs(ns) for ns in namespaces}
    pvs = get_pvs()

    vm_errors = []
    vm_aged = []
    pvc_errors = []
    pv_errors = []

    vm_total = 0
    vm_errors_count = 0
    vm_aged_count = 0
    pvc_total = 0
    pvc_errors_count = 0
    pv_total = 0
    pv_errors_count = 0

    # Available states:
    #   Stopped
    #   Provisioning
    #   Starting
    #   Running
    #   Paused
    #   Stopping
    #   Terminating
    #   Migrating
    #   WaitingForVolumeBinding
    #   Unknown
    #   Error
    for namespace in namespaces:
        vms = get_virtual_machines(namespace)
        vm_total += len(vms)
        for vm in vms:
            vm_name = vm['metadata']['name']
            vm_status, last_transition_time, age = check_vm_status(vm)
            # If we're in Stopping, Terminating, Migrating, Waiting..., Unknown, Error, or Starting for more than 30 minutes, count as error
            if vm_status in ["Stopping", "Terminating", "Migrating", "WaitingForVolumeBinding", "Unknown", "Error", "Starting"] and age.total_seconds() > 1800:
                vm_errors_count += 1
                vm_errors.append((vm_name, namespace, vm_status, age, format_age(age)))
            # If we're Provisioning for more than 2 hours, count as error
            if vm_status in ["Provisioning"] and age.total_seconds() > 7200:
                vm_errors_count += 1
                vm_errors.append((vm_name, namespace, vm_status, age, format_age(age)))
            # If we're Running, Paused, or Stopped for more than 2 weeks, count as error
            if vm_status in ["Running", "Paused", "Stopped"] and age.total_seconds() > 864000:
                vm_aged_count += 1
                vm_aged.append((vm_name, namespace, vm_status, age, format_age(age)))

        for pvc in pvcs[namespace]:
            pvc_name = pvc.metadata.name
            pvc_status, last_transition_time, age = check_pvc_status(pvc)
            pvc_total += 1
            if pvc_status != "Bound" and age.total_seconds() > 1800:
                pvc_errors_count += 1
                pvc_errors.append((pvc_name, namespace, pvc_status, age, format_age(age)))

    for pv in pvs:
        pv_name = pv.metadata.name
        pv_status, last_transition_time, age = check_pv_status(pv)
        pv_total += 1
        if pv_status != "Bound" and age.total_seconds() > 1800:
            pv_errors_count += 1
            pv_errors.append((pv_name, pv_status, age, format_age(age)))

    # Sort and print the oldest 25 errors for each type
    vm_aged.sort(key=lambda x: x[3], reverse=True)
    vm_errors.sort(key=lambda x: x[3], reverse=True)
    pvc_errors.sort(key=lambda x: x[3], reverse=True)
    pv_errors.sort(key=lambda x: x[2], reverse=True)

    if not vm_errors and not pvc_errors and not pv_errors:
        print("[OK] - All VMs, PVCs, and PVs are in a healthy state")
        exit(0)
    else:
        print(f"[WARNING] - Items in error-state found | vms_total={vm_total} vms_aged={vm_aged_count} vms_errors={vm_errors_count} pvcs_total={pvc_total} pvcs_errors={pvc_errors_count} pvs_total={pv_total} pvs_errors={pv_errors_count}")
        print("  VM Aged:")
        for error in vm_aged[:25]:
            print(f"    [WARN] - VM {error[0]} in {error[1]} status: {error[2]} age {error[4]}")
        print("  VM Errors:")
        for error in vm_errors[:25]:
            print(f"    [WARN] - VM {error[0]} in {error[1]} status: {error[2]} age {error[4]}")
        print("  PVC Errors:")
        for error in pvc_errors[:25]:
            print(f"    [WARN] - PVC {error[0]} in {error[1]} status: {error[2]} age {error[4]}")
        print("  PV Errors:")
        for error in pv_errors[:25]:
            print(f"    [WARN] - PV {error[0]} status: {error[1]} age {error[3]}")
        exit(1)


if __name__ == "__main__":
    main()
