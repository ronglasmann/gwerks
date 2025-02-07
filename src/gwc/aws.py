import re
import base64
import string
from ast import literal_eval
from time import time, sleep

import boto3
from botocore.exceptions import ClientError
from tenacity import stop_after_attempt, wait_fixed, retry_if_exception_type, retry

from . import environment, region, is_live_environment, is_dev_environment, ENV_KEY


# --------------------------------------------------------------------------- #
# returns the current aws credentials
def get_credentials():
    session = boto3.Session()
    credentials = session.get_credentials()
    return credentials.access_key, credentials.secret_key


# --------------------------------------------------------------------------- #
# AWS Secrets Manager
def get_secret(secret_name, region_name=None):

    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        if e.response['Error']['Code'] == 'DecryptionFailureException':
            # Secrets Manager can't decrypt the protected secret text using the provided KMS key.
            raise e
        elif e.response['Error']['Code'] == 'InternalServiceErrorException':
            # An error occurred on the server side.
            raise e
        elif e.response['Error']['Code'] == 'InvalidParameterException':
            # You provided an invalid value for a parameter.
            raise e
        elif e.response['Error']['Code'] == 'InvalidRequestException':
            # You provided a parameter value that is not valid for the current state of the resource.
            raise e
        elif e.response['Error']['Code'] == 'ResourceNotFoundException':
            # AWS can't find the resource that you asked for.
            raise e
    else:
        # Decrypts secret using the associated KMS CMK.
        # Depending on whether the secret is a string or binary, one of these fields will be populated.
        if 'SecretString' in get_secret_value_response:
            secret = get_secret_value_response['SecretString']
            return literal_eval(secret)
        else:
            code = get_secret_value_response['SecretBinary']

            b64_altchars = b'+/'
            b64_data = re.sub(rb'[^a-zA-Z0-9%s]+' % b64_altchars, b'', code)
            missing_padding = len(b64_data) % 4
            if missing_padding:
                b64_data += b'=' * (4 - missing_padding)
            decoded_binary_secret = base64.b64decode(b64_data, b64_altchars)
            # decoded_binary_secret = _decode_base64(code)

            return decoded_binary_secret


# --------------------------------------------------------------------------- #
# validates machine specs and provides convenient getter methods
class SpecHelper:

    # --------------------------------------------------------------------------- #
    # Validate
    def __init__(self, machine_spec):
        self.spec = machine_spec

        if 'type' not in self.spec:
            raise Exception('"type" is required in the machine spec')

        if 'size' not in self.spec:
            raise Exception('"size" is required in the machine spec')

        if 'role' not in self.spec:
            raise Exception('"role" is required in the machine spec')

        if 'service' not in self.spec:
            raise Exception('"service" is required in the machine spec')

        if 'purpose' not in self.spec:
            raise Exception('"purpose" is required in the machine spec')

        if 'volume_size' not in self.spec and 'root_volume_size' not in self.spec:
            raise Exception('Either "volume_size" or "root_volume_size" is required in the machine spec')

        if 'subnet' not in self.spec:
            raise Exception('"subnet" is required in the machine spec')

    # --------------------------------------------------------------------------- #
    # subclasses must implement these functions
    # --------------------------------------------------------------------------- #

    def _get_default_keypair_name(self):
        raise Exception(f"not implemented!")

    def _get_security_groups_by_instance_role_map(self):
        raise Exception(f"not implemented!")

    def _get_subnets_by_name_map(self):
        raise Exception(f"not implemented!")

    def _get_amis_by_instance_types_map(self):
        raise Exception(f"not implemented!")

    def _get_role_arns_by_instance_roles_map(self):
        raise Exception(f"not implemented!")

    # --------------------------------------------------------------------------- #
    # Returns value from spec or the default value
    def get(self, key, default_value=None):
        if key in self.spec:
            return self.spec[key]
        else:
            return default_value

    def get_key_pair_name(self):
        return self.get("key_pair_name", self._get_default_keypair_name())

    def get_security_groups(self):
        the_map = self._get_security_groups_by_instance_role_map()
        if self.get('role') in the_map:
            return the_map[self.get('role')]
        else:
            raise Exception(f"'{self.get('role')}' is an unrecognized role")

    def get_network_interfaces(self):
        sec_group_ids = self.get_security_groups()
        subnet_id = self.get_subnet()

        network_int = {
            'AssociatePublicIpAddress': self.get('assign_public_ip', True),
            'DeviceIndex': 0,
            'SubnetId': subnet_id,
            'Groups': sec_group_ids,
        }
        return network_int

    def get_subnet(self):
        the_map = self._get_subnets_by_name_map()
        subnet_name = self.get('subnet')
        if subnet_name in the_map:
            return the_map[subnet_name]
        else:
            raise Exception(f"'{subnet_name}' is an unrecognized subnet")

    def get_block_device_mappings(self):

        # get teh volume type or use the default
        root_volume_type = self.get("root_volume_type", "standard")

        root_device_name = '/dev/xvda'
        volume_letters = "fghijklmnop"

        if self.get('volume_size') is None:
            bdm = [{
                'DeviceName': root_device_name,
                'Ebs': {'VolumeSize': self.get('root_volume_size'), 'VolumeType': root_volume_type}
            }]
            # volume_letters = "fghijklmnop"
            if self.get('additional_volume_sizes') is not None:
                for volume_index in range(len(self.get('additional_volume_sizes'))):
                    bdm.append({
                        'DeviceName': f'/dev/xvd{volume_letters[volume_index]}',
                        'Ebs': {'VolumeSize': self.get('additional_volume_sizes')[volume_index],
                                'VolumeType': self.get('additional_volume_types')[volume_index]}
                    })
        else:
            bdm = [{
                'DeviceName': root_device_name,
                'Ebs': {'VolumeSize': self.get('volume_size'), 'VolumeType': root_volume_type}
            }]
        return bdm

    def get_ami(self):
        the_map = self._get_amis_by_instance_types_map()
        if self.get('type') in the_map:
            return the_map[self.get('type')]
        else:
            raise Exception(f"'{self.get('type')}' is an unrecognized type")

    def get_instance_role(self):
        the_map = self._get_role_arns_by_instance_roles_map()
        if self.get('role') in the_map:
            return {"Arn": the_map[self.get('role')]}
        else:
            raise Exception(f"'{self.get('role')}' is an unrecognized role")

    def get_elastic_ip_from_pool(self, region_name):
        pool_name = self.get('elastic_ip_from_pool')
        ec2_client = boto3.client('ec2', region_name=region_name)
        response = ec2_client.describe_addresses(
            Filters=[{'Name': 'tag:eip-pool', 'Values': [pool_name]}]
        )
        for eip_dict in response['Addresses']:
            if "InstanceId" in eip_dict:
                continue
            if "AssociationId" in eip_dict:
                continue
            # print(eip_dict)
            return eip_dict['PublicIp']
        raise Exception(f"No available IPs in elastic IP pool (eip_pool) '{pool_name}'")


# --------------------------------------------------------------------------- #
# Creates a standardized bootstrap script based on the spec machine type
class Bootstrap:

    COMPLETE_FILE = "hello_there_bootstrap_has_finished"

    def __init__(self, spec):
        self.__cmds__ = []
        self.__added_to_domain__ = False

        env_key = ENV_KEY
        env_val = environment()

        if not isinstance(spec, SpecHelper):
            spec = SpecHelper(spec)

        # self.__machine_name__ = machine_name
        self.__type__ = spec.get('type')

        # install os updates
        self.append_cmd('yum update -y')

        # timezone
        timezone = spec.get('timezone', "America/New_York")
        self.append_cmd(f"timedatectl set-timezone {timezone}")
        # self.append_cmd(f'cp /usr/share/zoneinfo/{timezone} /etc/localtime')

        # host name
        # self.append_cmd(f"hostnamectl set-hostname {machine_name}.{fqdn}")

        # set the system environment variable
        self.append_cmd(f'echo "{env_key}={env_val}" >> /etc/environment')

        # install ruby and pip and boto3
        self.append_cmd("yum install -y ruby")
        self.append_cmd('yum install python-pip -y')
        self.append_cmd('pip install boto3')

        # enable and start ssm
        self.append_cmd("sudo systemctl enable amazon-ssm-agent")
        self.append_cmd("sudo systemctl start amazon-ssm-agent")

    def append_cmd(self, cmd):
        self.__cmds__.append(cmd)

    def get_script(self):
        # create the "complete file" as the last bootstrap command
        if self.__type__ == LinuxInstance.TYPE:
            self.append_cmd(f"touch ./{Bootstrap.COMPLETE_FILE}")
        else:
            raise Exception(f"Unrecognized type: '{self.__type__}'")

        if len(self.__cmds__) == 0:
            return None

        ps = self._get_script_prefix()
        for cmd in self.__cmds__:
            ps += cmd + self._get_line_ending()
        ps += self._get_script_suffix()
        # print(ps)
        return ps

    def get_script_b64encoded(self):
        script = bytes(self.get_script(), 'utf-8')
        return base64.b64encode(script).decode("ascii")

    def _get_line_ending(self):
        if self.__type__ == LinuxInstance.TYPE:
            return "\n"
        else:
            raise Exception(f"Unrecognized type: '{self.__type__}'")

    def _get_script_prefix(self):
        if self.__type__ == LinuxInstance.TYPE:
            return "#!/bin/bash\n"
        else:
            raise Exception(f"Unrecognized type: '{self.__type__}'")

    def _get_script_suffix(self):
        if self.__type__ == LinuxInstance.TYPE:
            return ""
        else:
            raise Exception(f"Unrecognized type: '{self.__type__}'")


# --------------------------------------------------------------------------- #
# Encapsulates logic for binding to EC2 instances to copy files to them and/or
# configure them.  Tries to find an existing instance first.  Creates a new
# instance if one doesn't exist
class Instance:

    # --------------------------------------------------------------------------- #
    # Binds to the instance for the name and environment_name.  Creates it if necessary.
    def __init__(self, name, region_name=None, spec: SpecHelper = None, bootstrapper: Bootstrap = None):

        self.name = Instance._full_name(name)
        self.environment_name = environment()

        if region_name:
            self.region_name = region_name
        else:
            self.region_name = region()

        self._keypair_name = spec.get_key_pair_name()

        self.instance = None

        # does a machine with this name and environment_name already exist? If not, launch one
        try:
            self._bind()
            print(f'Binding to existing {Colors.grn}{self.name}{Colors.end}')
            if not self.is_ready():
                raise Exception(f'{Colors.grn}{self.name}{Colors.end} never entered a ready state, '
                                f'unable to continue')

        # no machine found, try to launch one
        except InstanceNotFound:
            if spec is None:
                raise InstanceNotFound(f'{Colors.grn}{self.name}{Colors.end} not in AWS '
                                      f'and a spec was not provided, unable to continue.')

            # no machine found, but we have a spec, launch a new machine
            else:
                # print(f'Launching {Colors.grn}{self.name}{Colors.end}')
                self._launch(spec, bootstrapper)
                if not self.is_ready():
                    raise Exception(f'{Colors.grn}{self.name}{Colors.end} never finished bootstrapping, '
                                    f'cannot continue')

        self.print_machine_info()

    # --------------------------------------------------------------------------- #
    # Tries to connect until successful or until retries are exhausted.
    def probe(self):
        raise Exception("not implemented!")

    # --------------------------------------------------------------------------- #
    # Returns True if the machine is bootstrapped and ready for configuration
    def is_ready(self):
        raise Exception("not implemented!")

    # --------------------------------------------------------------------------- #
    # Configure this machine by remotely sending commands to it
    def configure(self, commands):
        raise Exception("not implemented!")

    # --------------------------------------------------------------------------- #
    # runs the specified commands and interrogates the output for the
    # specified string
    def configure_and_verify(self, commands, validation_string):
        verified = False
        for line in self.configure(commands):
            # print(line)
            if validation_string in line:
                verified = True
                break
        return verified

    # --------------------------------------------------------------------------- #
    # Prints info about this machine to the console.
    def print_machine_info(self):
        print(f"Machine Name......... {self.name}")
        print(f"Environment.......... {self.environment_name}")
        print(f"Region.-----......... {self.region_name}")
        print(f"Instance Id.......... {self.instance_id}")
        print(f"Subnet............... {self.subnet} ({self.subnet_id})")
        print(f"Ip Address........... {self.host_ip_v4} ({self.host_ip_v4_type})")
        if self.host_ip_v4_private:
            print(f"Private Ip Address... {self.host_ip_v4_private}")
        if self.host_ip_v4_public:
            print(f"Public Ip Address.... {self.host_ip_v4_public}")
        if self.host_ip_v4_elastic:
            print(f"Elastic Ip Address... {self.host_ip_v4_elastic}")
        print(f"Platform............. {self.platform}")
        print(f"Tags................. {self.instance['Tags']}")
        print(f"State................ {self.instance['State']}")
        print(f"Termination Prot..... {self.is_termination_protected()}")

    # --------------------------------------------------------------------------- #
    # Toggles termination protection on and off
    def toggle_termination_protection(self):
        if self.is_spot_instance():
            print("Spot instances cannot be protected from accidental termination.")
            return
        toggle_to = not self.is_termination_protected()
        ec2_client = boto3.client('ec2', region_name=self.region_name)
        ec2_client.modify_instance_attribute(
            InstanceId=self.instance_id,
            Attribute="disableApiTermination",
            Value=str(toggle_to)
        )

    # --------------------------------------------------------------------------- #
    # Returns True if the machine is a spot instance
    def is_spot_instance(self):
        self._bind()
        # print(f'{self.instance}')
        if 'SpotInstanceRequestId' in self.instance:
            return True
        else:
            return False

    # --------------------------------------------------------------------------- #
    # Returns True if the machine has termination protection enabled
    def is_termination_protected(self):
        ec2_client = boto3.client('ec2', region_name=self.region_name)
        response = ec2_client.describe_instance_attribute(
            Attribute='disableApiTermination',
            InstanceId=self.instance_id
        )
        return response['DisableApiTermination']['Value']

    # --------------------------------------------------------------------------- #
    # Gets the value stored in teh specified tag or None if tag doesn't exist
    def get_value_from_tag(self, key):
        self._bind()  # make sure we have the latest tags
        for tag in self.instance['Tags']:
            if tag['Key'] == key:
                return tag['Value']
        return None

    # --------------------------------------------------------------------------- #
    # Sets all of the specified tags
    def apply_tags(self, tags):
        ec2_resource = boto3.resource('ec2', region_name=self.region_name)
        inst = ec2_resource.Instance(self.instance_id)
        inst.create_tags(Tags=tags)

    # --------------------------------------------------------------------------- #
    # associates this machine with an Elastic IP address.  If "elastic_ip" is not
    # found in AWS, an exception is thrown
    def associate_elastic_ip(self, elastic_ip):
        print(f'Associating {Colors.grn}{self.name}{Colors.end} ({self.instance_id}) with {elastic_ip}')
        # # allocation = ec2_client.allocate_address(Domain='vpc')
        allocation_id = None
        ec2_client = boto3.client('ec2', region_name=self.region_name)
        addresses_dict = ec2_client.describe_addresses()
        for eip_dict in addresses_dict['Addresses']:
            if "InstanceId" in eip_dict:
                continue
            if "AssociationId" in eip_dict:
                continue
            # print(eip_dict)
            if eip_dict['PublicIp'] == elastic_ip:
                allocation_id = eip_dict['AllocationId']

        if allocation_id is not None:
            ec2_client.associate_address(AllocationId=allocation_id,
                                         InstanceId=self.instance_id)
        else:
            raise Exception(f"Elastic IP {elastic_ip} is not available.  Has it "
                            f"been allocated?  Or is it already associated?")

    # --------------------------------------------------------------------------- #
    # Terminates the instance with the specified name in the current environment_name
    def terminate(self, force=False):
        instance_name = self._full_name()

        try:

            instance = self._find(False)
            if instance is None:
                raise InstanceNotFound

            # check that this machine was launched with the specified keypair
            if "KeyName" in instance:
                if instance['KeyName'] != self._keypair_name and not force:
                    raise Exception(f"{instance_name} is not associated with the {self._keypair_name} key pair.")

            # disable termination protection if not a spot instance
            if 'SpotInstanceRequestId' not in instance:
                ec2_client = boto3.client('ec2', region_name=self.region_name)
                # response = ec2_client.describe_instance_attribute(
                #     Attribute='disableApiTermination',
                #     InstanceId=instance['InstanceId']
                # )
                # if response['DisableApiTermination']['Value']:
                ec2_client.modify_instance_attribute(
                    InstanceId=instance['InstanceId'],
                    Attribute="disableApiTermination",
                    Value=str(False)
                )

            print(f'Terminating {Colors.grn}{self.name}{Colors.end} '
                  f'in the {Colors.grn}{environment()}{Colors.end} environment_name...')
            ec2_resource = boto3.resource('ec2', region_name=self.region_name)
            instance = ec2_resource.Instance(instance['InstanceId'])
            instance.terminate()

            # wait until the instance is gone
            print(f'Waiting for termination to complete... ', end='', flush=True)
            instance.wait_until_terminated()
            print(f'Done.')

        except InstanceNotFound:
            print(f'{Colors.grn}{instance_name}{Colors.end} not found, nothing to do.')

        except Exception as e:
            print(e)
            raise e

    # --------------------------------------------------------------------------- #
    # Stops the instance with the specified name in the current environment_name
    def stop(self):
        instance_name = self._full_name()

        try:

            instance = self._find(False)
            if instance is None:
                raise InstanceNotFound

            # check that this machine was launched with the specified keypair
            if "KeyName" in instance:
                if instance['KeyName'] != self._keypair_name:
                    raise Exception(f"{instance_name} is not associated with the {self._keypair_name} key pair.")

            print(f'Stopping {Colors.grn}{self.name}{Colors.end} '
                  f'in the {Colors.grn}{environment()}{Colors.end} environment_name...', end='', flush=True)
            ec2_client = boto3.client('ec2', region_name=self.region_name)
            ec2_client.stop_instances(InstanceIds=[instance['InstanceId']], DryRun=False)
            print(f'Done.')

        except InstanceNotFound:
            print(f'{Colors.grn}{instance_name}{Colors.end} not found, nothing to do.')

        except Exception as e:
            print(e)
            raise e

    # --------------------------------------------------------------------------- #
    # Starts the instance with the specified name in the current environment_name
    def start(self):
        instance_name = self._full_name()

        try:
            instance = self._find(False)
            if instance is None:
                raise InstanceNotFound

            # check that this machine was launched with the specified keypair
            if "KeyName" in instance:
                if instance['KeyName'] != self._keypair_name:
                    raise Exception(f"{instance_name} is not associated with the {self._keypair_name} key pair.")

            print(f'Starting {Colors.grn}{instance_name}{Colors.end} '
                  f'in the {Colors.grn}{environment()}{Colors.end} environment_name...', end='', flush=True)
            ec2_client = boto3.client('ec2', region_name=self.region_name)
            ec2_client.start_instances(InstanceIds=[instance['InstanceId']], DryRun=False)
            print(f'Done.')

        except InstanceNotFound:
            print(f'{Colors.grn}{instance_name}{Colors.end} not found, nothing to do.')

        except Exception as e:
            print(e)
            raise e

    # --------------------------------------------------------------------------- #
    # logic for creating machine names
    def _full_name(self):
        raw_name = self.name
        name = "".join([c for c in raw_name if c in string.ascii_letters or c in string.digits or c in '-_'])
        env = environment()
        if not is_live_environment():
            name += "-" + env
        return name

    # --------------------------------------------------------------------------- #
    # Finds a machine instance for the specified name
    def _find(self, normalize_name=True):
        m_name = self.name
        if normalize_name:
            instance_name = [self._full_name()]
        else:
            instance_name = [m_name]

        environment_list = [environment()]
        if is_dev_environment():
            environment_list.append("Development")
            instance_name.append(f"{instance_name[0]}elopment")

        # print(f"Looking for '{name}' in '{environment_name}'...")

        ec2_client = boto3.client('ec2', region_name=self.region_name)
        ec2_response = ec2_client.describe_instances(
            Filters=[
                {'Name': 'tag:Name', 'Values': instance_name},
                {'Name': 'tag:Environment', 'Values': environment_list},
            ],
        )
        found_instance = None
        if len(ec2_response['Reservations']) > 0:
            for r in ec2_response['Reservations']:
                for i in r['Instances']:
                    state = i['State']['Name']
                    if state != "terminated" and state != 'shutting-down':
                        if found_instance is not None:
                            # Highlander pattern, there can be only be one
                            raise Exception(f'Found more than one machine for {instance_name} + {environment_list}')
                        else:
                            found_instance = i
        return found_instance

    # --------------------------------------------------------------------------- #
    # Finds a machine instance for the name and environment_name
    def _bind(self):
        i = self._find(False)
        if i is not None:
            self.instance = i
            self.instance_id = i['InstanceId']

            self.availability_zone = i['Placement']['AvailabilityZone']

            # get the ip address(es)
            self.host_ip_v4_private = None
            self.host_ip_v4_public = None
            self.host_ip_v4_elastic = None
            if "PrivateIpAddress" in i:
                self.host_ip_v4_private = i["PrivateIpAddress"]
            if "PublicIpAddress" in i:
                self.host_ip_v4_public = i["PublicIpAddress"]
            ec2_client = boto3.client('ec2', region_name=self.region_name)
            addresses_dict = ec2_client.describe_addresses()
            for eip_dict in addresses_dict['Addresses']:
                if "InstanceId" in eip_dict and eip_dict["InstanceId"] == self.instance_id:
                    self.host_ip_v4_elastic = eip_dict["PublicIp"]
                    break
            # if self.host_ip_v4_elastic:
            #     self.host_ip_v4 = self.host_ip_v4_elastic
            #     self.host_ip_v4_type = "elastic"
            # elif self.host_ip_v4_public:
            #     self.host_ip_v4 = self.host_ip_v4_public
            #     self.host_ip_v4_type = "public"
            # else:
            self.host_ip_v4 = self.host_ip_v4_private
            self.host_ip_v4_type = "private"

            if "KeyName" in i:
                self.key_name = i['KeyName']
            else:
                self.key_name = "Unknown"

            if "Platform" in i:
                self.platform = i['Platform']

            # set the timestamp and name from the tags
            ts = None
            for tag in i['Tags']:
                if tag['Key'] == 'Timestamp':
                    ts = tag['Value']
                if tag['Key'] == 'Name':
                    self.name = tag['Value']
            if ts is not None:
                self._timestamp = ts
            # else:
            #     raise Exception(f'Machine {self.name_env()} does not have a Timestamp tag, unable to bind')
        else:
            raise InstanceNotFound(f'Machine {self.name} not found, unable to bind')

    # --------------------------------------------------------------------------- #
    # Launches a machine instance for the name, environment_name, and spec
    def _launch(self, machine_spec, bootstrapper):

        spec = SpecHelper(machine_spec)
        self.subnet = spec.get('subnet')
        self.subnet_id = spec.get_subnet()
        self.key_pair_name = spec.get_key_pair_name()

        self._timestamp = str(time())

        # bootstrap scripts
        if bootstrapper is None:
            bootstrapper = Bootstrap(spec)

        # launch a new spot instance
        if spec.get('launch_as_spot', False):
            self._launch_spot_instance(spec, bootstrapper)

        # create a new on demand instance
        else:
            self._launch_on_demand_instance(spec, bootstrapper)

        # apply tags immediately after the machine is up
        req_tags = [
            {'Key': 'Name', 'Value': f'{self.name}'},
            {'Key': 'Environment', 'Value': f'{self.environment_name}'},
            {'Key': 'Timestamp', 'Value': f'{self._timestamp}'},
            {'Key': 'Service', 'Value': f'{spec.get("service")}'},
            {'Key': 'Purpose', 'Value': f'{spec.get("purpose")}'},
            {'Key': 'ExpectedTTL', 'Value': f'{spec.get("expectedTTL")}'},
            {'Key': 'Instance-Type', 'Value': f'{spec.get("type")}'}
        ]
        print(f'Tagging {Colors.grn}{self.name}{Colors.end} ({self.instance_id}) with [{req_tags}')
        self.apply_tags(req_tags)
        if spec.get("tags") is not None:
            print(f'Tagging {Colors.grn}{self.name}{Colors.end} ({self.instance_id}) '
                  f'with [{spec.get("tags")}')
            self.apply_tags(spec.get("tags"))

        # associate elastic ip
        if spec.get("elastic_ip") is not None:
            self.associate_elastic_ip(spec.get("elastic_ip"))

        elif spec.get("elastic_ip_from_pool") is not None:
            # find an ip
            elastic_ip = spec.get_elastic_ip_from_pool(region_name=self.region_name)
            self.associate_elastic_ip(elastic_ip)

        # enable termination protection
        if spec.get("protect_from_termination", True):
            self.toggle_termination_protection()

        # bind to the new instance
        self._bind()

        # ensure we can connect
        if not self.is_ready():
            raise Exception(f'Unable to confirm {self.name} is ready, not safe to continue')

    def _launch_on_demand_instance(self, spec, bootstrapper):
        ec2_resource = boto3.resource('ec2', region_name=self.region_name)
        instance = ec2_resource.create_instances(
            ImageId=spec.get_ami(),
            InstanceType=spec.get('size'),
            KeyName=spec.get_key_pair_name(),
            BlockDeviceMappings=spec.get_block_device_mappings(),
            NetworkInterfaces=[spec.get_network_interfaces()],
            IamInstanceProfile=spec.get_instance_role(),
            UserData=bootstrapper.get_script(),
            MinCount=1,
            MaxCount=1
        )
        self.instance_id = instance[0].id
        print(f'Starting {Colors.grn}{self.name}{Colors.end} ({self.instance_id}) now... ',
              end='', flush=True)

        # waits until the instance is responsive
        instance[0].wait_until_running()
        print(f'Done.')

    def _launch_spot_instance(self, spec, bootstrapper, wait_time=30, retries=60):
        ec2_client = boto3.client('ec2', region_name=self.region_name)
        ec2_resource = boto3.resource('ec2', region_name=self.region_name)

        # request spot instance
        print(f'Requesting a spot instance for {Colors.grn}{self.name}{Colors.end}... ', end='')
        ec2_response = ec2_client.request_spot_instances(
            LaunchSpecification={
                'IamInstanceProfile': spec.get_instance_role(),
                'ImageId': spec.get_ami(),
                'InstanceType': spec.get('size'),
                'KeyName': spec.get_key_pair_name(),
                'BlockDeviceMappings': spec.get_block_device_mappings(),
                'NetworkInterfaces': [spec.get_network_interfaces()],
                'UserData': bootstrapper.get_script_b64encoded(),
            },
        )
        spot_request_id = self._parse_spot_instance_requests(ec2_response)
        print(spot_request_id)

        # wait for request to be fulfilled
        print(f'Getting instance id for {Colors.grn}{self.name}{Colors.end}... ', end='')
        while self.instance_id is None and retries > 0:
            sleep(wait_time)
            ec2_response = ec2_client.describe_spot_instance_requests(SpotInstanceRequestIds=[spot_request_id])
            self._parse_spot_instance_requests(ec2_response)
            if self.instance_id is None:
                print(f'Spot request not fulfilled yet, retrying in {wait_time} seconds, {retries} retries left...')
                retries -= 1
        if self.instance_id is None:
            raise Exception(f'Unable to fulfill spot request for {Colors.grn}{self.name}{Colors.end}')
        print(self.instance_id)

        # wait until the instance is running
        instance = ec2_resource.Instance(self.instance_id)
        instance.wait_until_running()
        print(f'Spot request for {Colors.grn}{self.name}{Colors.end} fulfilled and running.')

    def _parse_spot_instance_requests(self, ec2_response):
        spot_request_id = None
        spot_requests = ec2_response['SpotInstanceRequests']
        if len(spot_requests) != 1:  # there should be only one
            raise Exception(f"Unexpected response to spot instance request: {ec2_response}")
        elif 'Fault' in spot_requests[0]:
            raise Exception(f"Spot request error: {spot_requests[0]['Fault']['Message']}")
        elif 'InstanceId' in spot_requests[0]:
            self.instance_id = spot_requests[0]['InstanceId']
        else:
            self.instance_id = None

        if 'SpotInstanceRequestId' in spot_requests[0]:
            spot_request_id = spot_requests[0]['SpotInstanceRequestId']

        return spot_request_id


class InstanceNotFound(Exception):
    pass


class CommandInProgressException(Exception):
    pass


class LinuxInstance(Instance):

    TYPE = "linux-server"

    def __init__(self, name):
        super().__init__(name)
        self.platform = "aws linux"

    # --------------------------------------------------------------------------- #
    # Configure this machine by remotely sending commands to it
    def configure(self, commands, execution_timeout=3600, print_commands=True, print_output=True):

        if execution_timeout < 30:
            raise Exception("'execution_timeout' must be set to at least 30 seconds")

        # print the command that will be sent to the console
        exec_timeout = [str(execution_timeout)]
        for cmd in commands:
            if print_commands:
                print(f'{Colors.cyn}#>{cmd}{Colors.end}')  # in cyan

        ssm_client = boto3.client('ssm', region_name=self.region_name)
        response = ssm_client.send_command(
            InstanceIds=[self.instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={'commands': commands,
                        'executionTimeout': exec_timeout
                        },
        )
        # print(response)
        command_id = response['Command']['CommandId']

        sleep(3)  # need to wait just a couple seconds for the command to register

        num_status_retries = int(execution_timeout / 15)
        return self._ssm_status.retry_with(stop=stop_after_attempt(num_status_retries),
                                           wait=wait_fixed(15),
                                           retry=retry_if_exception_type(CommandInProgressException))(command_id, print_output)

    @retry(stop=stop_after_attempt(240), wait=wait_fixed(15), retry=retry_if_exception_type(CommandInProgressException))
    def _ssm_status(self, command_id, print_output=True):
        ssm_client = boto3.client('ssm', region_name=self.region_name)

        try:
            cmd_invocation_resp = ssm_client.get_command_invocation(
                CommandId=command_id,
                InstanceId=self.instance_id,
            )
            # print(cmd_invocation_resp)
        except Exception as e:
            print(f"{Colors.red}{e}{Colors.end}")
            raise CommandInProgressException(f"{e}")

        if 'StatusDetails' not in cmd_invocation_resp:
            print(f"{Colors.red}Status not available for command {command_id}{Colors.end}")
            raise CommandInProgressException(f"Status not available for command {command_id}")

        output = ''
        status = cmd_invocation_resp['StatusDetails']
        if status.lower() == 'success':
            print(f"Command {command_id}: {Colors.grn}{status}{Colors.end}")
            # print(cmd_invocation_resp)
            if 'StandardOutputContent' in cmd_invocation_resp:
                output += cmd_invocation_resp['StandardOutputContent']
            if 'StandardErrorContent' in cmd_invocation_resp and \
                    len(cmd_invocation_resp['StandardErrorContent'].strip()) > 0:
                output += Colors.red + cmd_invocation_resp['StandardErrorContent'] + Colors.end
            # if len(output.strip()) <= 0:
            #     output = status
            if len(output.strip()) > 0:
                lines = output.splitlines()
                if print_output:
                    for ln in lines:
                        print(f'{Colors.grn}{ln.strip()}{Colors.end}')  # in green
                return lines
            else:
                return None
        elif status.lower() in [
            'delivery timed out', 'execution timed out', 'failed', 'canceled', 'undeliverable', 'terminated',
            'invalid platform', 'access denied'
        ]:
            print(f"Command {command_id}: {Colors.red}{status}{Colors.end}")
            raise Exception(f'Error processing command {command_id} on instance {self.instance_id}: {status}')
        else:
            print(f"Command {command_id}: {Colors.red}{status}{Colors.end}")
            raise CommandInProgressException(f"{status}")

    def probe(self):
        print(f"SSM status for {self.instance_id} is... ", end='')
        ssm_client = boto3.client('ssm', region_name=self.region_name)
        ssm_resp = ssm_client.get_connection_status(Target=self.instance_id)['Status']
        if ssm_resp == "connected":
            print(f"{Colors.grn}{ssm_resp}{Colors.end}")
            return True
        else:
            print(f"{Colors.red}{ssm_resp}{Colors.end}")
            return False

    # --------------------------------------------------------------------------- #
    # waits for ssh to activate and then looks for the "bootstrap complete" file
    # in the home folder
    @retry(stop=stop_after_attempt(60), wait=wait_fixed(15))
    def is_ready(self):

        # ensure the system is online
        if not self.probe():
            # print(f"{instance_id} is {Colors.red}not online{Colors.end}")
            raise Exception(f"{self.instance_id} is not online or ready for commands")

        output = self.configure(['ls -l /'], print_output=False, print_commands=False)
        # print(output)
        for line in output:
            if Bootstrap.COMPLETE_FILE not in line:
                continue
            else:
                print(f"{self.instance_id} is {Colors.grn}ready{Colors.end}")
                return True
        else:
            # print(f"not ready")
            print(f"{self.instance_id} is {Colors.red}not bootstrapped{Colors.end}")
            raise Exception(f"Bootstrap complete file not found on {self.instance_id}")


class Colors:
    # terminal colors
    red = "\033[0;31m"
    cyn = "\033[0;36m"
    grn = "\033[0;32m"
    end = "\033[0m"
