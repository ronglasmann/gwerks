import os
import socket
import shutil
import tempfile
from io import StringIO

import yaml
from smart_open import open

import gwerks.aws as aws
from gwerks import environment, is_dev_environment, region, profile, uid
from gwerks.util.sys import sudo, exec_cmd
from gwerks.decorators import emitter


# TODO implement DockerHost to enable management of servers capable of hosting Docker containers on various platforms
# TODO implement docker repos other than ECR


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
            exec_cmd(f"service docker start || true", no_sudo=is_dev_environment())

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
        result, exit_code = exec_cmd(f"docker ps", raise_exc=False, no_sudo=is_dev_environment(), return_tuple=True)
        # exit_code = result.returncode
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
        exec_cmd(f"docker system prune -f", no_sudo=is_dev_environment())

    # --------------------------------------------------------------------------- #
    # service docker start
    @staticmethod
    def stop():
        if DockerService.is_running():
            exec_cmd(f"service docker stop || true", no_sudo=is_dev_environment())


class DockerNetwork:

    # --------------------------------------------------------------------------- #
    # network driver names
    DRIVER_BRIDGE = "bridge"
    DRIVER_HOST = "host"
    DRIVER_OVERLAY = "overlay"
    DEFAULT_DRIVER = DRIVER_BRIDGE

    DRIVERS = [DRIVER_BRIDGE, DRIVER_HOST, DRIVER_OVERLAY]

    def __init__(self, name, driver=DEFAULT_DRIVER):
        self._name = name
        self._driver = driver

        if self._driver not in DockerNetwork.DRIVERS:
            raise Exception(f"driver must be one of {DockerNetwork.DRIVERS}, not '{self._driver}'")

        if self._driver in [DockerNetwork.DRIVER_BRIDGE, DockerNetwork.DRIVER_OVERLAY]:
            if self._name is None:
                raise Exception(f"DockerNetwork.name must be specified when creating {self._driver} network")

        self._create()

    # --------------------------------------------------------------------------- #
    # docker network create
    def _create(self):
        DockerService.ensure_running()
        if self._driver == DockerNetwork.DRIVER_BRIDGE:
            cmd = f"docker network inspect {self._name} >/dev/null 2>&1 " \
                  f"|| {sudo(no_sudo=is_dev_environment())} docker network create --driver {self._driver} {self._name}"
        else:
            cmd = f"docker network create --driver {self._driver} "
        exec_cmd(cmd, no_sudo=is_dev_environment())

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
        exec_cmd(f"docker network rm {self._name} || true", no_sudo=is_dev_environment())


class DockerApp:

    # @emitter(mod_name="DockerApp")
    def __init__(self, app_name, image_name):
        self._app_name = app_name
        print(f"app_name: {app_name}")
        self._image_name = image_name
        print(f"image_name: {image_name}")

        self._host_name = socket.gethostname()
        # print(f"host_name: {self._host_name}")
        self._host_ip = socket.gethostbyname(self._host_name)
        # print(f"host_ip: {self._host_ip}")

        self._ecr_repo = None

    def get_app_name(self):
        return self._app_name

    def get_image_name(self):
        return self._image_name

    def get_host_name(self):
        return self._host_name

    def get_host_addr(self):
        return self._host_ip

    # @emitter(mod_name="DockerApp")
    def _full_image_name(self):
        if not self._image_name:
            raise Exception(f"image is None")
        docker_image = self._image_name
        if self._ecr_repo is not None:
            docker_image = f"{self._ecr_repo}/{self._image_name}"
        print(f"full_image_name: {docker_image}")
        return docker_image

    # --------------------------------------------------------------------------- #
    # docker pull
    # @emitter(mod_name="DockerApp")
    def pull(self, docker_image_version="latest"):
        DockerService.ensure_running()
        exec_cmd(f"docker pull {self._full_image_name()}:{docker_image_version}", no_sudo=is_dev_environment())

    # --------------------------------------------------------------------------- #
    # docker run
    # @emitter(mod_name="DockerApp")
    def run(self, app_cmd: str, network: DockerNetwork = None, port_mappings: list[tuple] = None,
            volume_mappings: list[tuple] = None, log_group_prefix: str = "/"):
        DockerService.ensure_running()

        cmd = f"docker run --name {self._app_name} --env APP_NAME={self._app_name} "
        cmd += f"--env RUNTIME_ENV={environment()} --env PYTHONUNBUFFERED=1 "

        if network is not None:
            cmd += f"--network {network.get_name()} "

        # expose ports
        if port_mappings and len(port_mappings) > 0:
            for pm in port_mappings:
                host_port = pm[0]
                cont_port = pm[1]
                cmd += f"-p {host_port}:{cont_port} "

        # map volumes
        if volume_mappings and len(volume_mappings) > 0:
            for vm in volume_mappings:
                host_vol = vm[0]
                cont_vol = vm[1]
                cmd += f"-v {host_vol}:{cont_vol} "

        # use the aws log driver in Test and Live so the logs go to Cloudwatch
        if not is_dev_environment():
            # if not log_group_base:
            #     raise Exception(f"Unspecified log_group_base for the {environment_name()} environment_name")
            log_group = log_group_prefix
            log_group += f"/{environment()}/{self._host_name}"
            if not log_group.startswith("/"):
                log_group = "/" + log_group
            if log_group.endswith("/"):
                log_group = log_group[:-1]

            cmd += f"--log-driver=awslogs "
            cmd += f"--log-opt awslogs-group={log_group} --log-opt awslogs-create-group=true "
            cmd += f"--log-opt awslogs-stream={self._app_name} "

        # in the Dev environment_name expect AWS keys must be set in the system environment_name
        if is_dev_environment():
            cmd += f"--env AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID "
            cmd += f"--env AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY "

        cmd += f"-d -i {self._full_image_name()} "
        cmd += f"{app_cmd}"

        # print(cmd)
        exec_cmd(cmd, no_sudo=is_dev_environment())

        print(f"Running!")

    # --------------------------------------------------------------------------- #
    # docker stop
    # @emitter(mod_name="DockerApp")
    def stop(self):
        DockerService.ensure_running()
        exec_cmd(f"docker stop {self._app_name} || true", no_sudo=is_dev_environment())
        exec_cmd(f"docker wait {self._app_name} || true", no_sudo=is_dev_environment())

    # --------------------------------------------------------------------------- #
    # docker rm
    # @emitter(mod_name="DockerApp")
    def remove(self):
        DockerService.ensure_running()
        exec_cmd(f"docker rm {self._app_name} || true", no_sudo=is_dev_environment())

    # --------------------------------------------------------------------------- #
    # docker login
    def set_ecr_repo(self, ecr_repo):
        DockerService.ensure_running()
        if ecr_repo is None:
            raise Exception(f"ecr_repo must be specified")
        cmd = f"aws ecr get-login-password --region {region()} --profile {profile()} "
        cmd += "| "
        cmd += f"docker login --username AWS --password-stdin {ecr_repo} "
        exec_cmd(cmd, no_sudo=is_dev_environment())
        self._ecr_repo = ecr_repo


@emitter()
class DockerContext:
    def __init__(self, config: dict = None, from_yaml_file: str = None, from_yaml_str: str = None, ):

        self._config = config
        if not self._config:
            self._config = {}

        # open the yaml and parse it
        if from_yaml_file:
            print(f"loading yaml file {from_yaml_file}")
            with open(from_yaml_file, 'r') as f:
                self._config = yaml.safe_load(f)

        elif from_yaml_str:
            self._config = yaml.safe_load(StringIO(from_yaml_str))

        if "files" not in self._config.keys():
            self._config["files"] = ["."]

        if "use_buildkit" not in self._config.keys():
            self._config["use_buildkit"] = "True"

        the_build_context = uid("docker_build_context")
        self._tar_file_name = f"{the_build_context}.tar.gz"
        self._build_context_fp = f"{tempfile.gettempdir()}/{the_build_context}"

        # self._build()

    def to_yaml_file(self, yaml_file_path: str):
        with open(yaml_file_path, 'w') as f:
            yaml.dump(self._config, f, sort_keys=False)

    def set(self, key, value):
        self._config[key] = value

    @emitter()
    def build(self, image_name, no_cache=False):

        self._create()
        DockerService.ensure_running()

        try:
            cmd = ""
            if self._config.get("use_buildkit") == "True":
                cmd += f"DOCKER_BUILDKIT=1 "
            cmd += f"docker build "
            if no_cache:
                cmd += "--no-cache "
            if self._config.get("pass_through_cloud_creds") == "aws":
                access_key, secret_key = aws.get_credentials()
                cmd += f"--build-arg AWS_ACCESS_KEY_ID={access_key} "
                cmd += f"--build-arg AWS_SECRET_ACCESS_KEY={secret_key} "
            cmd += f"-t {image_name} "
            cmd += f"- < {self._tar_file_name } "
            exec_cmd(cmd, no_sudo=is_dev_environment())

        finally:
            self._destroy()

    def _create(self):
        if not os.path.exists(self._build_context_fp):
            print(f"makedirs: {self._build_context_fp}")
            os.makedirs(self._build_context_fp)

        if 'files' in self._config.keys():
            for file in self._config["files"]:
                self._copy_from(file)

        if 'dockerfile_str' in self._config.keys():
            self._write_dockerfile()
        elif 'dockerfile_file' in self._config.keys():
            if not self._copy_from(self._config['dockerfile_file']):
                raise Exception(f"copying {self._config['dockerfile_file']} failed")
        else:
            raise Exception(f"either 'dockerfile_str' or 'dockerfile_file' must be specified")

        cmd = ""
        cmd += f"tar -C {self._build_context_fp} -czf {self._tar_file_name} ."
        exec_cmd(cmd, no_sudo=is_dev_environment())

    # @emitter()
    def _write_dockerfile(self):
        the_dockerfile = f"{self._build_context_fp}/Dockerfile"
        print(f"write: {the_dockerfile}")
        with open(the_dockerfile, 'w') as f:
            f.write(self._config['dockerfile_str'])

    # @emitter()
    def _copy_from(self, copy_src):
        tgt = self._build_context_fp
        if type(copy_src) is list:
            src = copy_src[0]
            tgt += f"/{copy_src[1]}"
        else:
            src = copy_src

        if os.path.exists(src):
            if os.path.isfile(src):
                print(f"copy {src} -> {tgt}")
                shutil.copy(src, tgt)
            elif os.path.isdir(src):
                print(f"copytree {src} -> {self._build_context_fp}")
                shutil.copytree(src, self._build_context_fp,
                                symlinks=False, ignore_dangling_symlinks=True, dirs_exist_ok=True,
                                ignore=shutil.ignore_patterns('build*', 'data*', 'dist*', ".git*", ".github*"))
            else:
                print(f"WARN: ignored {src} (exists, not file, not dir)")
                return False
        else:
            print(f"WARN: ignored {src} (does not exist)")
            return False

        return True

    # @emitter()
    def _destroy(self):
        cmd = ""
        cmd += f"rm {self._tar_file_name} && rm -rf {self._build_context_fp}"
        exec_cmd(cmd, no_sudo=is_dev_environment())
