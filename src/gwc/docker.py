import os
import socket

import aws
from . import environment, is_dev_environment, region, profile


class DockerHost:
    def __init__(self):
        pass

    def launch(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def terminate(self):
        pass


class DockerService:

    # --------------------------------------------------------------------------- #
    # service docker start
    @staticmethod
    def start():
        if not DockerService.is_running():
            execute_cmd(f"service docker start || true")

    # --------------------------------------------------------------------------- #
    # raise exc if service is not running
    @staticmethod
    def ensure_running():
        if not DockerService.is_running():
            raise Exception(f"Docker service is not running")

    # --------------------------------------------------------------------------- #
    # use docker info to see if Docker is running
    @staticmethod
    def is_running():
        exit_code = execute_cmd(f"docker info", raise_exc=False)
        return exit_code == 0

    # --------------------------------------------------------------------------- #
    # docker system prune
    # removes: all stopped containers
    #          all networks not used by at least one container
    #          all images without at least one container associated to them
    #          all build cache
    @staticmethod
    def prune():
        DockerService.ensure_running()
        execute_cmd(f"docker system prune -f")

    # --------------------------------------------------------------------------- #
    # service docker start
    @staticmethod
    def stop():
        if DockerService.is_running():
            execute_cmd(f"service docker stop || true")


class DockerNetwork:

    # --------------------------------------------------------------------------- #
    # network driver names
    DRIVER_BRIDGE = "bridge"
    DRIVER_HOST = "host"
    DEFAULT_DRIVER = DRIVER_BRIDGE

    def __init__(self, name, driver=DEFAULT_DRIVER):
        self._name = name
        self._driver = driver

        if self._driver == DockerNetwork.DRIVER_BRIDGE:
            if self._name is None:
                raise Exception(f"net_name was None when creating {self._driver} network")

        self._create()

    # --------------------------------------------------------------------------- #
    # docker network create
    def _create(self):
        DockerService.ensure_running()
        if self._driver == DockerNetwork.DRIVER_BRIDGE:
            cmd = f"docker network inspect {self._name} >/dev/null 2>&1 " \
                  f"|| {sudo()} docker network create --driver {self._driver} {self._name}"
        else:
            cmd = f"docker network create --driver {self._driver} "
        execute_cmd(cmd)

    # --------------------------------------------------------------------------- #
    # return the network name
    def get_name(self):
        return self._name

    # --------------------------------------------------------------------------- #
    # docker network rm
    def destroy(self):
        DockerService.ensure_running()
        if self._name is None:
            raise Exception(f"net_name was None when destroying network")
        execute_cmd(f"docker network rm {self._name} || true")


class DockerApp:

    def __init__(self, app_name, app_cmd, image_name, log_group_prefix=None, network: DockerNetwork = None):
        self._app_name = app_name
        self._app_cmd = app_cmd
        self._image_name = image_name
        self._network = network

        self._host_name = socket.gethostname()
        self._host_ip = socket.gethostbyname(self._host_name)

        self._log_group = ""
        if log_group_prefix is not None:
            self._log_group += f"/{log_group_prefix}"
        self._log_group += f"/{environment()}/{self._host_name}"

        self._ecr_repo = None
        self._port_mappings = []
        self._volume_mappings = []

    def get_app_name(self):
        return self._app_name

    def get_image_name(self):
        return self._image_name

    def get_host_name(self):
        return self._host_name

    def get_host_addr(self):
        return self._host_ip

    def get_network(self):
        return self._network

    def set_network(self, network: DockerNetwork):
        self._network = network

    def _full_image_name(self):
        if not self._image_name:
            raise Exception(f"image is None")
        docker_image = self._image_name
        if self._ecr_repo is not None:
            docker_image = f"{self._ecr_repo}/{self._image_name}"
        return docker_image

    # --------------------------------------------------------------------------- #
    # docker pull
    def pull(self, docker_image_version="latest"):
        DockerService.ensure_running()
        execute_cmd(f"docker pull {self._full_image_name()}:{docker_image_version}")

    # --------------------------------------------------------------------------- #
    # delegates to run
    def start(self):
        self.run()

    # --------------------------------------------------------------------------- #
    # docker run
    def run(self):
        DockerService.ensure_running()

        cmd = f"docker run --name {self._app_name} --env APP_NAME={self._app_name} "
        cmd += f"--env RUNTIME_ENV={environment()} --env PYTHONUNBUFFERED=1 "

        if self._network is not None:
            cmd += f"--network {self._network.get_name()} "

        # expose ports
        if self._port_mappings and len(self._port_mappings) > 0:
            for pm in self._port_mappings:
                host_port = pm[0]
                cont_port = pm[1]
                cmd += f"-p {host_port}:{cont_port} "

        # map volumes
        if self._volume_mappings and len(self._volume_mappings) > 0:
            for vm in self._volume_mappings:
                host_vol = vm[0]
                cont_vol = vm[1]
                cmd += f"-v {host_vol}:{cont_vol} "

        # use the aws log driver in Test and Live so the logs go to Cloudwatch
        if not is_dev_environment():
            # if not log_group_base:
            #     raise Exception(f"Unspecified log_group_base for the {environment_name()} environment_name")
            cmd += f"--log-driver=awslogs "
            cmd += f"--log-opt awslogs-group={self._log_group} --log-opt awslogs-create-group=true "
            cmd += f"--log-opt awslogs-stream={self._app_name} "

        # in the Dev environment_name expect AWS keys must be set in the system environment_name
        if is_dev_environment():
            cmd += f"--env AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID "
            cmd += f"--env AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY "

        cmd += f"-d -i {self._full_image_name()} "
        cmd += f"{self._app_cmd}"

        # print(cmd)
        execute_cmd(cmd)

    # --------------------------------------------------------------------------- #
    # docker stop
    def stop(self):
        DockerService.ensure_running()
        execute_cmd(f"docker stop {self._app_name} || true")
        execute_cmd(f"docker wait {self._app_name} || true")

    # --------------------------------------------------------------------------- #
    # delegates to remove
    def shut_down(self):
        self.remove()

    # --------------------------------------------------------------------------- #
    # docker rm
    def remove(self):
        DockerService.ensure_running()
        execute_cmd(f"docker rm {self._app_name} || true")

    # --------------------------------------------------------------------------- #
    # docker login
    def set_ecr_repo(self, ecr_repo):
        DockerService.ensure_running()
        if ecr_repo is None:
            raise Exception(f"ecr_repo must be specified")
        cmd = f"aws ecr get-login-password --region {region()} --profile {profile()} "
        cmd += "| "
        cmd += f"docker login --username AWS --password-stdin {ecr_repo} "
        execute_cmd(cmd)
        self._ecr_repo = ecr_repo

    # --------------------------------------------------------------------------- #
    # docker login
    def build(self, build_context_path, pass_aws_creds_to_image=False, use_buildkit=True):
        DockerService.ensure_running()

        if not build_context_path:
            raise Exception(f"build_context_path is None, unable to build")

        if not self._image_name:
            raise Exception(f"_image_name is None, unable to build")

        cmd = ""
        cmd += f"tar -C {build_context_path} -czf fwq.tar.gz ."
        execute_cmd(cmd)

        cmd = ""
        if use_buildkit:
            cmd += f"DOCKER_BUILDKIT=1 "
        cmd += f"docker build "
        # cmd += f"docker build -f {dockerfile_file_path} "
        if pass_aws_creds_to_image:
            access_key, secret_key = aws.get_credentials()
            cmd += f"--build-arg AWS_ACCESS_KEY_ID={access_key} "
            cmd += f"--build-arg AWS_SECRET_ACCESS_KEY={secret_key} "
        cmd += f"-t {self._image_name} "
        cmd += f"- < fwq.tar.gz "
        # cmd += ". "
        execute_cmd(cmd)

        cmd = ""
        cmd += f"rm fwq.tar.gz"
        execute_cmd(cmd)


# --------------------------------------------------------------------------- #
# execute system command, optionally raise Exceptions on non-zero exit codes
def execute_cmd(cmd, raise_exc=True):
    print(f"execute_cmd: {cmd}")
    exit_code = os.system(f"{sudo()} {cmd}")
    if raise_exc and exit_code != 0:
        raise Exception(f"{cmd} failed with exit code {exit_code}")
    return exit_code


# --------------------------------------------------------------------------- #
# run commands as root outside the Dev environment_name
def sudo():
    if is_dev_environment():
        return ""
    return "sudo"
