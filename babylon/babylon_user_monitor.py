#! /usr/bin/python3

"""
description       :This monitor validates the data-integrity of babylon users based on integrity from the UserNamespaces entities
author            :jappleii@redhat.com (John Apple II), yvarbev@redhat.com (Yordan Varbev)
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import argparse
import kubernetes
import os
import datetime
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

# Pull current time
now = datetime.datetime.utcnow()
# Currently hard coded to 24 hours
seconds_for_time_comparison = 86400

parser = argparse.ArgumentParser(description='Monitor for Babylon User data-integrity ')
parser.add_argument('-a', '--apiurl', help='address of the API e.g. "https://host.localdomain.com/api:4321"', required=True, type=str, dest='apiurl')
parser.add_argument('-s', '--secret-file', help='file path containing the k8s secret for the API', required=True, type=str, dest='secret_path')
parser.add_argument('-c', '--cacert', help='file path containing CA Cert for API', required=True, type=str, dest='cacert')
parser.add_argument('-p', '--isprimary', help='Defaults to false, but add this flag if this is the the primary cluster running babylon and babylon-ui', required=False, action='store_true', dest='isprimary')
args = parser.parse_args()

# setup the client
# apikey = Path('/path/to/my/secret/token').read_text()
apikey = Path(args.secret_path).read_text()
aConfig = kubernetes.client.Configuration()
aConfig.api_key = {"authorization": "Bearer " + apikey}
aConfig.host = args.apiurl
# aConfig.host = "https://my.ocp.babylon.cluster:6443"
# aConfig.ssl_ca_cert = '/path/to/my/cluster.crt'
aConfig.ssl_ca_cert = args.cacert
aApiClient = kubernetes.client.ApiClient(aConfig)
# ocp_client = DynamicClient(aApiClient)
custom_objects_api = kubernetes.client.CustomObjectsApi(aApiClient)
v1 = kubernetes.client.CoreV1Api(aApiClient)

# Pull all resources required
# custom_resources = ocp_client.resources.get(api_version='apiextensions.k8s.io/v1beta1', kind='CustomResourceDefinition')
# usergroupmembers = custom_objects_api.list_cluster_custom_object('usergroup.pfe.redhat.com', 'v1', 'usergroupmembers')['items']
# projects = ocp_client.resources.get(api_version='project.openshift.io/v1', kind='Project')
# project_list = projects.get().to_dict()
namespace_dict = {}
user_last_login_list = []
user_dict = {}
identity_dict = {}
rolebinding_dict = {}
group_dict = {}
#
usernamespaces = custom_objects_api.list_cluster_custom_object('usernamespace.gpte.redhat.com', 'v1', 'usernamespaces')['items']
###
# Process namespaces, rolebindings, users, identities, and groups into dicts
###
namespaces = v1.list_namespace().to_dict()["items"]
namespacecount = len(namespaces)
for namespace in namespaces:
    namespace_dict[namespace["metadata"]["name"]] = ""
del(namespaces)
#
rolebindings = custom_objects_api.list_cluster_custom_object('rbac.authorization.k8s.io', 'v1', 'rolebindings')['items']
for rolebinding in rolebindings:
    rolebinding_dict[rolebinding["metadata"]["name"]] = ""
del(rolebindings)
#
users = custom_objects_api.list_cluster_custom_object('user.openshift.io', 'v1', 'users')['items']
for user in users:
    user_dict[user["metadata"]["name"]] = {}
    try:
        user["identities"]
    except Exception:
        user_dict[user["metadata"]["name"]]["identities"] = [] 
    else:
        user_dict[user["metadata"]["name"]]["identities"] = user["identities"]
    # Test user last login and fill last-login list
    try:
        useless = user["metadata"]["annotations"]
        useless = user["metadata"]["annotations"]['<annotation>/last-login']
    except Exception:
        pass
    else:
        user_last_login_list.append(user["metadata"]["annotations"]['<annotation>/last-login'])
del(users)
#
identities = custom_objects_api.list_cluster_custom_object('user.openshift.io', 'v1', 'identities')['items']
for identity in identities:
    identity_dict[identity["metadata"]["name"]] = {}
    try:
        identity["extra"]["email"]
    except Exception:
        identity_dict[identity["metadata"]["name"]]["email"] = ""
    else:
        identity_dict[identity["metadata"]["name"]]["email"] = identity["extra"]["email"]
del(identities)
#
groups = custom_objects_api.list_cluster_custom_object('user.openshift.io', 'v1', 'groups')['items']
for group in groups:
    group_dict[group["metadata"]["name"]] = {}
    group_dict[group["metadata"]["name"]]["users"] = group["users"]
del(groups)
### DEBUGGING
#pprint(namespace_dict)
#pprint(user_dict)
#pprint(identity_dict)
#pprint(rolebinding_dict)
#pprint(group_dict)
#pprint(usernamespaces[6]["status"]["managedResources"][0]["name"])
#pprint(usernamespaces[6]["status"]["managedResources"][0]["namespace"])

# Run the last-login logic first.
## Rules:
#### 1. The last 10 logins are considered. If less than 10, we consider it an error
#### 2. Each of these logins must occur less than 24 hours in the past.
## If those conditions are not met, raise a warning.
###
## Logic:
### 1. Pull each annotation into an array for all users in the cluster
### 2. Sort the Array (Standard ISO datetime format sorts cleanly)
### 3. Check that array has at least 10 entries
### 4. Slice the last 10 entries off into their own list and delete the original
### 5. Test the first entry and compare if it is within 24 hours.
### If this passes, We have passed the last-login test and are good
### Else, we have a failure - report how many days in the past the last-login occurred.
#
#Prestage our boolean and...
last_login_error = False
lastloginerror = False
last_login_error_string = ""
#
# Check that we have at least 10 entries in the list
#
if len(user_last_login_list) < 10:
    lastloginerror = True
    last_login_error_string = f"WARNING - Less than 10 logins on the cluster!"
# all of our logic for the date-time tests goes in the else clause, so we skip additional work.
else:
    # Now that we know that we have 10 items, sort and pull last ten entries into a slice (which is also sorted)
    user_last_login_list.sort()
    ten_slice = user_last_login_list[-10:-1]
    datetime_ten = datetime.datetime.strptime(ten_slice[0],"%Y-%m-%dT%H:%M:%SZ")
    timedelta = now - datetime_ten
    seconds_since_creation = int(timedelta.total_seconds())
    if seconds_since_creation > seconds_for_time_comparison:
        lastloginerror = True
        last_login_error_string = f"Last-login WARN - 10th logins back > 24hr at {ten_slice[1]}"
    else:
        lastloginerror = False
        last_login_error_string = "Last-login OK - 10 or more logins < 24hr"

# del(userDS)
# Initialize the datastructure
userDS = {}
# We sync our list using the UserNamespace Resource
for userns in usernamespaces:
    # Create the username top-level entry
    myusername = userns["spec"]["user"]["name"]
    userDS[myusername] = {}
    # Create Error Condition Fields
    userDS[myusername]["isinerror"] = False
    userDS[myusername]["errorflags"] = ""
    # Create project entry and confirm it exists
    userDS[myusername]["project"] = {}
    userDS[myusername]["project"]["name"] = userns["metadata"]["name"]
    try:
        namespace_dict[userns["metadata"]["name"]]
    except Exception:
        userDS[myusername]["project"]["exists"] = False
    else:
        userDS[myusername]["project"]["exists"] = True
    userDS[myusername]["rolebindings"] = []
    # Create the Rolebinding entry for the project
    for managedresource in userns["status"]["managedResources"]:
        try:
            rolebinding_dict[managedresource["name"]]
        except Exception:
            userDS[myusername]["rolebindings"].append({"name": managedresource["name"], "exists": False})
        else:
            userDS[myusername]["rolebindings"].append({"name": managedresource["name"], "exists": True})
    # Initialize the identities, create individual entries per identity
    # and confirm id providers exist and username is a member
    userDS[myusername]["identities"] = {}
    try:
        user_dict[myusername]
    except Exception:
        pass
    else:
        if user_dict[myusername]["identities"]:
            userDS[myusername]["identities"] = {}
            for identity in user_dict[myusername]["identities"]:
                # Setting up User Identities and ID Provider
                userDS[myusername]["identities"][identity] = {}
                myprovidername = identity.split(':')[0]
                myprovidergroup = "identity-provider." + myprovidername
                userDS[myusername]["identities"][identity]["groupname"] = myprovidergroup
                userDS[myusername]["identities"][identity]["ismember"] = False
                userDS[myusername]["identities"][identity]["exists"] = False
                try:
                    group_dict[myprovidergroup]
                except Exception:
                    pass
                else:
                    userDS[myusername]["identities"][identity]["exists"] = True
                    if group_dict[myprovidergroup]["users"]:
                        for group_user in group_dict[myprovidergroup]["users"]:
                            if myusername == group_user:
                                userDS[myusername]["identities"][identity]["ismember"] = True
                                break
                    else:
                        userDS[myusername]["identities"][identity]["ismember"] = False
                # Setting up User Emails and Email Provider
                userDS[myusername]["emails"] = {}
                try:
                    identity_dict[identity]["email"]
                except Exception:
                    pass
                else:
                    userDS[myusername]["emails"][identity_dict[identity]["email"]] = ""
                # Setup email group
                userDS[myusername]["email_groups"] = {}
                for email in userDS[myusername]["emails"]:
                    domain = email.split('@')[1]
                    myemailgroup = "email-domain." + domain
                    userDS[myusername]["email_groups"][myemailgroup] = {}
                    userDS[myusername]["email_groups"][myemailgroup]["exists"] = False
                    userDS[myusername]["email_groups"][myemailgroup]["ismember"] = False
                    try:
                        group_dict[myemailgroup]
                    except Exception:
                        pass
                    else:
                        userDS[myusername]["email_groups"][myemailgroup]["exists"] = True
                        for emailgroupmember_user in group_dict[myemailgroup]["users"]:
                            if emailgroupmember_user == myusername:
                                userDS[myusername]["email_groups"][myemailgroup]["ismember"] = True
                                break
        else:
            userDS[myusername]["isinerror"] = True
            # userDS[myusername]["errorflags"] = "userHasNoIdentities," ### TESTED TO HERE - JAII 2022-11-25

# Debug the datastructure
# pprint(userDS)

# Testing False setting
# userDS["jappleii@redhat.com"]["email_groups"]["email-domain.redhat.com"]["ismember"] = False

# Prepare to count errors
usercount = len(usernamespaces)
errorcount = 0
exitstring = ""

# Parse datastructure for errors
for user in userDS:
    # Check EmailGroups Flags
    for emailgroup in userDS[user]["email_groups"]:
        if userDS[user]["email_groups"][emailgroup]["exists"] is False:
            errorcount = errorcount + 1
            userDS[user]["errorflags"] += "noEmailGroup,"
            userDS[user]["isinerror"] = True
        if userDS[user]["email_groups"][emailgroup]["ismember"] is False:
            errorcount = errorcount + 1
            userDS[user]["errorflags"] += "notInEmailGroup,"
            userDS[user]["isinerror"] = True
    # Check Identity and ID group Flags
    identity_count = 0
    for identity in userDS[user]["identities"]:
        identity_count = identity_count + 1
        if userDS[user]["identities"][identity]["exists"] is False:
            errorcount = errorcount + 1
            userDS[user]["errorflags"] += "noIDGroup,"
            userDS[user]["isinerror"] = True
        if userDS[user]["identities"][identity]["ismember"] is False:
            errorcount = errorcount + 1
            userDS[user]["errorflags"] += "notInIDGroup,"
            userDS[user]["isinerror"] = True
    # if identity_count > 1:
        # errorcount = errorcount + 1
        # userDS[user]["errorflags"] += "tooManyIdentities,"
        # userDS[user]["isinerror"] = True
    # Check Project Flags
    if userDS[user]["project"]["exists"] is False:
        errorcount = errorcount + 1
        userDS[user]["errorflags"] += "noProject,"
        userDS[user]["isinerror"] = True
    # Check Rolebindings
    for rolebinding in userDS[user]["rolebindings"]:
        if rolebinding["exists"] is False:
            errorcount = errorcount + 1
            userDS[user]["errorflags"] += "noRolebinding,"
            userDS[user]["isinerror"] = True

# if this is not a primary cluster, we'll report the last_login info, then don't use this to create an error
# But still report status
if not args.isprimary:
    lastloginerror = False

if errorcount == 0 and not lastloginerror:
    exitstring = "[OK] No Babylon Users in Error found; | namespaces=" + str(namespacecount) + ";;;;; users=" + str(usercount) + ";;;;; errors=" + str(errorcount) + ";;;;; "
    exitstring += os.linesep + last_login_error_string
    print(exitstring)
    exit(0)
elif errorcount == 0 and lastloginerror:
    exitstring = "[WARNING] Last login has an error; | namespaces=" + str(namespacecount) + ";;;;; users=" + str(usercount) + ";;;;; errors=" + str(errorcount) + ";;;;; "
    exitstring += os.linesep + last_login_error_string
    print(exitstring)
    exit(1)
elif errorcount > 0 and not lastloginerror:
    exitstring = "[WARNING] Users in Error;| namespaces=" + str(namespacecount) + ";;;;; users=" + str(usercount) + ";;;;; errors=" + str(errorcount) + ";;;;; "
    exitstring += os.linesep + last_login_error_string
    for user in userDS:
        if userDS[user]["isinerror"] is True:
            exitstring = exitstring + os.linesep + user + ": " + userDS[user]["errorflags"]
    print(exitstring)
    exit(1)
elif errorcount > 0 and lastloginerror:
    exitstring = "[WARNING] Users in Error and last user login error;| namespaces=" + str(namespacecount) + ";;;;; users=" + str(usercount) + ";;;;; errors=" + str(errorcount) + ";;;;; "
    exitstring += os.linesep + last_login_error_string
    for user in userDS:
        if userDS[user]["isinerror"] is True:
            exitstring = exitstring + os.linesep + user + ": " + userDS[user]["errorflags"]
    print(exitstring)
    exit(1)
