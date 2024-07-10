#! /usr/bin/python3

"""
description       :This monitor checks the integrity of an anarchysubject object.
author            :jappleii@redhat.com (John Apple II), yvarbev@redhat.com (Yordan Varbev)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import kubernetes
import datetime
from pathlib import Path

parser = argparse.ArgumentParser(description='Monitor for Anarchy Subject data-integrity ')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api:4321"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the k8s secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-c', '--cacert', help='file path containing CA Cert for API', required=True, type=str, dest='cacert')
parser.add_argument('-d', '--deeplink', help='where to link the output', required=False, type=str, dest='deeplink',
                    default="https://my.babylonui.example.com/admin/anarchysubjects/")
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
anarchysubjects = custom_objects_api.list_cluster_custom_object('anarchy.gpte.redhat.com', 'v1', 'anarchysubjects')['items']

good_statuses = ['provision-pending', 'provisioning', 'started', 'start-pending', 'starting', 'stopped', 'stop-pending', 'stopping', 'destroying']
bad_statuses = ['provision-failed', 'start-failed', 'stop-failed', 'destroy-failed']
anarchysubjects_in_error = []
recovered = []

for anarchysubject in anarchysubjects:
    if anarchysubject["metadata"]["name"] == "babylon":
        continue
    d1 = datetime.datetime.strptime(anarchysubject["metadata"]["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ")
    now = datetime.datetime.utcnow()
    timedelta = now - d1
    seconds_since_creation = int(timedelta.total_seconds())
    mon_status = []
  
    try:
        anarchysubject["status"]["towerJobs"]["provision"]
    except Exception:
        if seconds_since_creation > (60 + 1800):  # 30 minutes added at request of prutledge
        entryJob = True
        mon_status.append("provisionJobMissing")
  
    try:
        anarchysubject["status"]["kopf"]["progress"]
    except Exception:
        pass
    else:
        if anarchysubject["status"]["kopf"]["progress"]:
            mon_status.append("kopfprogressExists")
        else:
            recovered.append(anarchysubject)
  
    try:
        anarchysubject["spec"]["vars"]["desired_state"]
    except Exception:
        mon_status.append("badDesiredStatus")
    else:
        if (anarchysubject["spec"]["vars"]["desired_state"] in good_statuses):
            pass
        else:
            mon_status.append("badDesiredStatus")
  
    try:
        anarchysubject["spec"]["vars"]["current_state"]
    except Exception:
        pass
    else:
        if (anarchysubject["spec"]["vars"]["current_state"] in bad_statuses):
            mon_status.append("badCurrentStatus")
  
    if mon_status:
        anarchysubject["mon_status"] = mon_status
        anarchysubjects_in_error.append(anarchysubject)

if len(anarchysubjects_in_error) == 0:
    exitstring = "[OK] No Anarchy Subjects in Error found; | countsubjects={};;;;; errorsubjects={};;;;; recovered={};;;;; ".format(
               len(anarchysubjects), len(anarchysubjects_in_error), len(recovered))
    print(exitstring)
    exit(0)
else:
    exitstring = "[WARNING] {err} Anarchy Subjects in Error found; | countsubjects={total};;;;; errorsubjects={err};;;;; recovered={re};;;;; ".format(
               err=len(anarchysubjects_in_error), total=len(anarchysubjects), re=len(recovered))
    print(exitstring)
    for subject in anarchysubjects_in_error:
        url = "{}{}/{}".format(args.deeplink, subject["metadata"]["namespace"], subject["metadata"]["name"])
        urlsubject = "<a target=\"_blank\" href=\"{}\">{}</a>".format(url, subject["metadata"]["name"])
        print(urlsubject, "-", *subject["mon_status"], "<br>")
    exit(1)
