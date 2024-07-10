#! /usr/bin/python3

"""
description       :This monitor checks the vmware cluster for usage of datastores and host cpu and memory usage
author            :jappleii@redhat.com (John Apple II) - with help from ChatGPT 4o especially on fixing SOAP queries
license           :Apache License v2
output            :Nagios/Icinga2 format
"""

import sys
import json
import requests
import xml.etree.ElementTree as ET
import argparse
from pprint import pprint

# Disable SSL warnings for self-signed certificates
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Nagios check for VMware vSphere.")
parser.add_argument('--secrets', type=str, required=True, help="Path to the secrets JSON file.")
parser.add_argument('--debug', type=bool, required=False, help="Enable Debug output.")
parser.add_argument('--datastore_warning', type=int, required=True, help="Datastore used space warning threshold in percentage.")
parser.add_argument('--datastore_critical', type=int, required=True, help="Datastore used space critical threshold in percentage.")
parser.add_argument('--cpu_warning', type=int, required=True, help="CPU usage warning threshold in percentage.")
parser.add_argument('--cpu_critical', type=int, required=True, help="CPU usage critical threshold in percentage.")
parser.add_argument('--memory_warning', type=int, required=True, help="Memory usage warning threshold in percentage.")
parser.add_argument('--memory_critical', type=int, required=True, help="Memory usage critical threshold in percentage.")
args = parser.parse_args()

# Load secrets from the provided file path
with open(args.secrets, 'r') as f:
    secrets = json.load(f)

vsphere_host = secrets['vsphere_host']
username = secrets['username']
password = secrets['password']

session = requests.Session()
session.verify = False

# Function to send a SOAP request


def send_soap_request(url, headers, data):
    response = session.post(url, headers=headers, data=data)
    response.raise_for_status()
    return response.text

# Function to logout


def logout():
    logout_xml = '''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:vim25">
       <soapenv:Header/>
       <soapenv:Body>
          <urn:Logout>
             <_this type="SessionManager">SessionManager</_this>
          </urn:Logout>
       </soapenv:Body>
    </soapenv:Envelope>
    '''
    try:
        send_soap_request(url, headers, logout_xml)
    except Exception as e:
        print(f"Failed to logout: {e}")
#   else:
#       print("Logged out")


try:
    # Convert thresholds to percentages
    datastore_warning_pct = args.datastore_warning
    datastore_critical_pct = args.datastore_critical
    cpu_warning_pct = args.cpu_warning
    cpu_critical_pct = args.cpu_critical
    memory_warning_pct = args.memory_warning
    memory_critical_pct = args.memory_critical

    # Authenticate and get the session cookie
    login_xml = '''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:vim25">
       <soapenv:Header/>
       <soapenv:Body>
          <urn:Login>
             <_this type="SessionManager">SessionManager</_this>
             <userName>{username}</userName>
             <password>{password}</password>
          </urn:Login>
       </soapenv:Body>
    </soapenv:Envelope>
    '''.format(username=username, password=password)
    # At this point I didn't think this was going to be so bad, these SOAP queries are simple and straightforward. Easy peasy - why do people hate SOAP???

    headers = {'Content-Type': 'text/xml', 'SOAPAction': 'urn:vim25/6.5'}
    url = f'https://{vsphere_host}/sdk'
    response = send_soap_request(url, headers, login_xml)

    # Retrieve the root folder MoRef
    retrieve_service_content_xml = '''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:vim25">
       <soapenv:Header/>
       <soapenv:Body>
          <urn:RetrieveServiceContent>
             <_this type="ServiceInstance">ServiceInstance</_this>
          </urn:RetrieveServiceContent>
       </soapenv:Body>
    </soapenv:Envelope>
    '''
    # Easy queries, right?

    response = send_soap_request(url, headers, retrieve_service_content_xml)
    root = ET.fromstring(response)
    # namespaces = {'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/', 'urn': 'urn:vim25'}
    namespaces = {'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/', 'urn': 'urn:vim25', 'vim25': 'urn:vim25'}
    root_folder_moref = root.find('.//urn:rootFolder', namespaces).text
    if args.debug:
        print(f"Root Folder MoRef: {root_folder_moref}")

    # Retrieve the cluster MoRef
    retrieve_clusters_xml = '''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:vim25">
       <soapenv:Header/>
       <soapenv:Body>
          <urn:RetrieveProperties>
             <_this type="PropertyCollector">propertyCollector</_this>
             <specSet>
                <propSet>
                   <type>ClusterComputeResource</type>
                   <all>false</all>
                   <pathSet>name</pathSet>
                </propSet>
                <objectSet>
                   <obj type="Folder">group-d1</obj>
                   <skip>false</skip>
                   <selectSet xsi:type="urn:TraversalSpec" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
                      <name>visitFolders</name>
                      <type>Folder</type>
                      <path>childEntity</path>
                      <skip>false</skip>
                      <selectSet>
                         <name>visitFolders</name>
                      </selectSet>
                      <selectSet xsi:type="urn:TraversalSpec">
                         <name>dcToHf</name>
                         <type>Datacenter</type>
                         <path>hostFolder</path>
                         <skip>false</skip>
                         <selectSet>
                            <name>visitFolders</name>
                         </selectSet>
                      </selectSet>
                      <selectSet xsi:type="urn:TraversalSpec">
                         <name>crToH</name>
                         <type>ComputeResource</type>
                         <path>host</path>
                         <skip>false</skip>
                      </selectSet>
                      <selectSet xsi:type="urn:TraversalSpec">
                         <name>crToRp</name>
                         <type>ComputeResource</type>
                         <path>resourcePool</path>
                         <skip>false</skip>
                         <selectSet>
                            <name>rpToRp</name>
                         </selectSet>
                      </selectSet>
                      <selectSet xsi:type="urn:TraversalSpec">
                         <name>rpToRp</name>
                         <type>ResourcePool</type>
                         <path>resourcePool</path>
                         <skip>false</skip>
                         <selectSet>
                            <name>rpToRp</name>
                         </selectSet>
                      </selectSet>
                   </selectSet>
                </objectSet>
             </specSet>
          </urn:RetrieveProperties>
       </soapenv:Body>
    </soapenv:Envelope>
    '''
    # Oh.  This is why people hate SOAP.  I also hate SOAP - I consider the risks of remaining unwashed for weeks on end after this query.

    response = send_soap_request(url, headers, retrieve_clusters_xml)
    root = ET.fromstring(response)
    cluster_moref = None

    for obj_content in root.findall('.//vim25:returnval/vim25:obj', namespaces):
        cluster_moref = obj_content.text
        if args.debug:
            print(f"Cluster MoRef: {cluster_moref}")
        break

    if not cluster_moref:
        print("No cluster found.")
        sys.exit(1)

    # Retrieve datastore details
    retrieve_datastore_xml = '''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:vim25" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
       <soapenv:Header/>
       <soapenv:Body>
          <urn:RetrieveProperties>
             <_this type="PropertyCollector">propertyCollector</_this>
             <specSet>
                <propSet>
                   <type>Datastore</type>
                   <all>false</all>
                   <pathSet>summary.name</pathSet>
                   <pathSet>summary.capacity</pathSet>
                   <pathSet>summary.freeSpace</pathSet>
                </propSet>
                <objectSet>
                   <obj type="Folder">{root_folder_moref}</obj>
                   <skip>false</skip>
                   <selectSet xsi:type="urn:TraversalSpec">
                      <name>visitFolders</name>
                      <type>Folder</type>
                      <path>childEntity</path>
                      <skip>false</skip>
                      <selectSet xsi:type="urn:TraversalSpec">
                         <name>dcToDs</name>
                         <type>Datacenter</type>
                         <path>datastore</path>
                         <skip>false</skip>
                      </selectSet>
                   </selectSet>
                </objectSet>
             </specSet>
          </urn:RetrieveProperties>
       </soapenv:Body>
    </soapenv:Envelope>
    '''.format(root_folder_moref=root_folder_moref)
    # Please God, no!  NO NO! _Author begins crying into his water

    response = send_soap_request(url, headers, retrieve_datastore_xml)
    if args.debug:
        print("datastore response:")
        pprint(response)
    # Parse the response
    root = ET.fromstring(response)

    # Find all returnval elements
    datastores = root.findall('.//urn:returnval', namespaces)

    # Dictionary to store datastore information
    datastore_info = {}

    # Extract capacity and used values
    for ds in datastores:
        datastore = {}
        name = None

        # Get object_moref
        object_moref = ds.find('urn:obj', namespaces).text
        datastore['object_moref'] = object_moref
        for prop in ds.findall('urn:propSet', namespaces):
            prop_name = prop.find('urn:name', namespaces).text
            prop_value = prop.find('urn:val', namespaces).text
            if args.debug:
                pprint(prop_name + " " + prop_value)
                print("----------------")
            if prop_name == 'summary.name':
                datastore['name'] = prop_value
            elif prop_name == 'summary.capacity': 
                datastore['capacity'] = int(prop_value)
            elif prop_name == 'summary.freeSpace':
                datastore['freeSpace'] = int(prop_value)

            if 'name' in datastore and 'capacity' in datastore and 'freeSpace' in datastore:
                datastore['used'] = int(datastore['capacity'] - datastore['freeSpace'])
                datastore['used_pct'] = float((datastore['used'] / datastore['capacity']) * 100)
                if args.debug:
                    pprint(datastore)
                datastore_info[object_moref] = datastore
                if args.debug:
                    print("----------------")
        if args.debug:
            print("--------b2--------")
        # Print the datastore information
        if args.debug:
            for name, info in datastore_info.items():
                print(f"Datastore Name: {name}")
                print(f"Object MoRef: {info['object_moref']}")
                print(f"Total Capacity: {info['capacity']} bytes")
                print(f"Free Space: {info['freeSpace']} bytes")
                print(f"Used Space: {info['used']} bytes")
                print("----------------------------")
    if args.debug:            
        pprint(datastore_info)

    # Retrieve host details
    retrieve_hosts_xml = '''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:urn="urn:vim25" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
       <soapenv:Header/>
       <soapenv:Body>
          <urn:RetrieveProperties>
             <_this type="PropertyCollector">propertyCollector</_this>
             <specSet>
                <propSet>
                   <type>HostSystem</type>
                   <all>false</all>
                   <pathSet>name</pathSet>
                   <pathSet>hardware.memorySize</pathSet>
                   <pathSet>summary.quickStats.overallMemoryUsage</pathSet>
                   <pathSet>summary.hardware.cpuMhz</pathSet>
                   <pathSet>summary.hardware.numCpuCores</pathSet>
                   <pathSet>summary.quickStats.overallCpuUsage</pathSet>
                </propSet>
                <objectSet>
                   <obj type="ComputeResource">{cluster_moref}</obj>
                   <skip>false</skip>
                   <selectSet xsi:type="urn:TraversalSpec">
                      <name>crToH</name>
                      <type>ComputeResource</type>
                      <path>host</path>
                      <skip>false</skip>
                   </selectSet>
                </objectSet>
             </specSet>
          </urn:RetrieveProperties>
       </soapenv:Body>
    </soapenv:Envelope>
    '''.format(cluster_moref=cluster_moref)
    #  This query took DAYS to figure out.  I began to hate life.  Waking up was sweet releif, because only XML/SOAP haunted my dreams.
    #  I began eyeing dull spoons from the flatware drawer and my family watched me with concern.
    #  Stabbing a leg with one dulls the pain, did you know that? Mostly because it takes forever and does minimal damage with maximum pain!

    response = send_soap_request(url, headers, retrieve_hosts_xml)
    # Parse the response
    root = ET.fromstring(response)
    # Find all returnval elements
    hosts = root.findall('.//urn:returnval', namespaces)
    # Dictionary to store host information
    host_info = {}

    # Extract host details
    for host in hosts:
        host_data = {}
        name = None
        # Get object_moref
        object_moref = host.find('urn:obj', namespaces).text
        #host_data['object_moref'] = object_moref
        if args.debug:
            print(object_moref)
        for prop in host.findall('urn:propSet', namespaces):
            prop_name = prop.find('urn:name', namespaces).text
            prop_value = prop.find('urn:val', namespaces).text
            if args.debug:
                pprint(prop_name + " :  " + prop_value)

            if prop_name == 'name':
                host_data['name'] = str(prop_value)
            elif prop_name == 'hardware.memorySize':
                host_data['memorySize'] = int(prop_value)
            elif prop_name == 'summary.quickStats.overallMemoryUsage':
                host_data['memoryUsage'] = int(prop_value)
            elif prop_name == 'summary.hardware.cpuMhz':
                host_data['cpuMhz'] = int(prop_value)
            elif prop_name == 'summary.hardware.numCpuCores':
                host_data['numCpuCores'] = int(prop_value)
            elif prop_name == 'summary.quickStats.overallCpuUsage':
                host_data['cpuUsage'] = int(prop_value)

        if args.debug:
            pprint(host_data)
            print("---3----")
        if 'name' in host_data and 'memorySize' in host_data and 'cpuMhz' in host_data and 'numCpuCores' in host_data:
            if args.debug:
                print("---4----")
            host_data['cpuTotalMhz'] = int(host_data['cpuMhz'] * host_data['numCpuCores'])
            host_data['cpu_usage_pct'] = float((host_data['cpuUsage'] / host_data['cpuTotalMhz']) * 100)
            host_data['memory_usage_pct'] = float((host_data['memoryUsage'] / host_data['memorySize']) * 100)
            host_info[object_moref] = host_data
        if args.debug:
            pprint(host_info)
            print("---5----")
            pprint(host_info)
            print("---6----")
            # Print the host information

# Step 6: Calculate all Values needed for State Check vs Expected and Prepare Nagios Output datastructure.
        global_critical_state = 0
        global_warning_state = 0
        output = {}
        output["Hosts"] = {}
        for name, info in host_info.items():
            output["Hosts"][name] = {}
            output["Hosts"][name]["commonname"] = {info['name']}
            output["Hosts"][name]["cpu"] = {}
            output["Hosts"][name]["cpu"]["pct"] = '%.3f'%float(info['cpu_usage_pct'])
            output["Hosts"][name]["cpu"]["total"] = info['cpuTotalMhz']
            output["Hosts"][name]["cpu"]["used"] = info['cpuUsage']
            output["Hosts"][name]["cpu"]["status"] = "[OK]"  # Default to Good Status
            output["Hosts"][name]["mem"] = {}
            output["Hosts"][name]["mem"]["pct"] = '%.5f'%float(info['memory_usage_pct'])
            output["Hosts"][name]["mem"]["total"] = '%.2f'%float(info['memorySize'] / 1073741824)
            output["Hosts"][name]["mem"]["used"] = '%.2f'%float(info['memoryUsage'] / 1073741824)
            output["Hosts"][name]["mem"]["status"] = "[OK]"  # Default to Good Status

            if args.debug:
                print("----7----")
                print(f"Host ObjMoref: {name}")
                print(f"Host Name: {info['name']}")
                print(f"Total Memory: {info['memorySize']} bytes")
                print(f"Memory Usage: {info['memoryUsage']} bytes")
                print(f"Total CPU: {info['cpuTotalMhz']} MHz")
                print(f"CPU Usage: {info['cpuUsage']} MHz")
                print(f"CPU Usage Pct: {info['cpu_usage_pct']}")
                print(f"Mem Usage Pct: {info['memory_usage_pct']}")
                print("----------------------------")
                print("----8----")

            if info['cpu_usage_pct'] > cpu_critical_pct:
                if args.debug:
                    print("ccritical")
                output["Hosts"][name]["cpu"]["status"] = "[CRITICAL]"
                global_critical_state = 1
            elif info['cpu_usage_pct'] > cpu_warning_pct:
                if args.debug:
                    print("cwarn")
                output["Hosts"][name]["cpu"]["status"] = "[WARNING]"
                global_warning_state = 1
            else:
                if args.debug:
                    print("cok")

            if info['memory_usage_pct'] > memory_critical_pct:
                if args.debug:
                    print("mcritical")
                output["Hosts"][name]["mem"]["status"] = "[CRITICAL]"
                global_critical_state = 1
            elif info['memory_usage_pct'] > memory_warning_pct:
                if args.debug:
                    print("mwarn")
                output["Hosts"][name]["mem"]["status"] = "[WARNING]"
                global_warning_state = 1
            else:
                if args.debug:
                    print("mok")
            if output["Hosts"][name]["mem"]["status"] == "[CRITICAL]" or output["Hosts"][name]["cpu"]["status"] == "[CRITICAL]":
                output["Hosts"][name]["status"] = "[CRITICAL]"
            elif output["Hosts"][name]["mem"]["status"] == "[WARNING]" or output["Hosts"][name]["cpu"]["status"] == "[WARNING]":
                output["Hosts"][name]["status"] = "[WARNING]"
            else:
                output["Hosts"][name]["status"] = "[OK]"
        if args.debug:
            pprint(hosts)
            pprint("-----nagiosstring-----")
            pprint(output)
            print("----9----")

    # Check datastore statuses
        output["Datastores"] = {}
        for ds in datastore_info:
            moref = datastore_info[ds]['object_moref']
            output["Datastores"][moref] = {}
            output["Datastores"][moref]["commonname"] = datastore_info[ds]['name']
            output["Datastores"][moref]["totalGB"] = '%.1f' % float(datastore_info[ds]['capacity'] / 1073741824)  # Covert bytes to GB 
            output["Datastores"][moref]["usedGB"] = '%.1f' % float(datastore_info[ds]['used'] / 1073741824)  # Covert bytes to GB 
            output["Datastores"][moref]["pct"] = '%.3f' % (float(datastore_info[ds]['used_pct']))
            output["Datastores"][moref]["freeGB"] = '%.1f' % float(datastore_info[ds]['freeSpace'] / 1073741824)  # Covert bytes to GB 
            output["Datastores"][moref]["status"] = "[OK]"  # Default to Good Status
            if args.debug:
                print("--------b--------")
                print(ds)
                pprint(output)
                print("--------c--------")
            if datastore_info[ds]['used_pct'] > datastore_critical_pct:
                output["Datastores"][moref]["status"] = "[CRITICAL]"  # Default to Good Status
                datastore_status = "CRITICAL"
                global_critical_state = 1
            elif datastore_info[ds]['used_pct'] > datastore_warning_pct:
                output["Datastores"][moref]["status"] = "[WARNING]"  # Default to Good Status
                datastore_status = "WARNING"
                global_warning_state = 1
            else:
                if args.debug:
                    print("ds status OK")
        # Print Nagios-style output
        if args.debug:
            print("----finaloutput------")
            pprint(output)
            print("----finaloutput------")
    if global_critical_state:
        global_status = "[CRITICAL]"
        the_exit_code = 2
    elif global_warning_state:
        global_status = "[WARNING]"
        the_exit_code = 1
    else:
        global_status = "[OK]"
        the_exit_code = 0

    # Print out the Nagios status-string
    print(f"{global_status} for VSphere/ESXi cluster")
    print("--------------")
    for category in output:
        print(category + ":")
        for entity in output[category]:
            print("\t" + entity + ": " + output[category][entity]["status"])
            if category == "Hosts":
                print("\t\tcpu: " + str(output[category][entity]["cpu"]["status"]) + " " + str(output[category][entity]["cpu"]["total"]) + " Mhz, " + str(output[category][entity]["cpu"]["pct"]) + "% used")
                print("\t\tmem: " + str(output[category][entity]["mem"]["status"]) + " " + str(output[category][entity]["mem"]["total"]) + " GiB, " + str(output[category][entity]["mem"]["pct"]) + "% used")
            else:
                print("\t\t" + str(output[category][entity]["commonname"]) + ": " + str(output[category][entity]["totalGB"]) + " GiB, " + str(output[category][entity]["usedGB"]) + " GiB Used, " + str(output[category][entity]["pct"]) + "% used")

    sys.exit(the_exit_code)

except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(1)

finally:
    logout()
# I hate SOAP.
