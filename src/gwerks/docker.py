import os
import socket
import shutil
import tempfile
from typing import Optional

from smart_open import open

from . import aws
from . import environment, is_dev_environment, region, profile, uid
from .util.sys import sudo, exec_cmd
from .decorators import emitter


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
    def assert_is_running():
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
        DockerService.assert_is_running()
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
        self._driver = None
        self.set_driver(driver)

    # --------------------------------------------------------------------------- #
    # return the network name
    def get_name(self):
        return self._name

    # return the network driver
    def get_driver(self):
        return self._driver

    # set the network driver
    def set_driver(self, driver):
        if driver not in DockerNetwork.DRIVERS:
            raise Exception(f"driver must be one of {DockerNetwork.DRIVERS}, not '{driver}'")

        if driver in [DockerNetwork.DRIVER_BRIDGE, DockerNetwork.DRIVER_OVERLAY]:
            if self._name is None:
                raise Exception(f"DockerNetwork.name must be specified when creating {driver} network")

        self._driver = driver

    # --------------------------------------------------------------------------- #
    # docker network create
    def create(self):
        DockerService.assert_is_running()
        if self._driver == DockerNetwork.DRIVER_BRIDGE:
            cmd = f"docker network inspect {self._name} >/dev/null 2>&1 " \
                  f"|| {sudo(no_sudo=is_dev_environment())} docker network create --driver {self._driver} {self._name}"
        else:
            cmd = f"docker network create --driver {self._driver} "
        exec_cmd(cmd, no_sudo=is_dev_environment())

    # --------------------------------------------------------------------------- #
    # docker network rm
    def destroy(self):
        DockerService.assert_is_running()
        if self._name is None:
            raise Exception(f"net_name was None when destroying network")
        exec_cmd(f"docker network rm {self._name} || true", no_sudo=is_dev_environment())


class DockerBase:
    def __init__(self, config):

        self._network: Optional[DockerNetwork] = None
        self._sys_name: Optional[str] = None
        self._host_name: Optional[str] = None
        self._name = self.__class__.__name__

        if "port" not in config:
            raise Exception("port is required")
        self._port = config["port"]

        if "image_name" not in config:
            raise Exception("image_name is required")
        self._image_name = config["image_name"]

        self._run_as = (os.getuid(), os.getgid())
        if "run_as" in config:
            self._run_as = config["run_as"]

        self._mem_max = None
        if "mem_max" in config:
            self._mem_max = config["mem_max"]

        self._mem_res = None
        if "mem_res" in config:
            self._mem_res = config["mem_res"]

        self._swap_max = None
        if "swap_max" in config:
            self._swap_max = config["swap_max"]

        self._published_ports = []
        if "published_ports" in config:
            self._published_ports = config["published_ports"]
        self._published_ports.append(self.get_port())

        self._volume_mappings = []
        if "volume_mappings" in config:
            self._volume_mappings = config["volume_mappings"]

        # docker build settings

        self._use_buildkit = True
        if "docker_use_buildkit" in config:
            self._use_buildkit = config["docker_use_buildkit"]

        self._docker_app_files = []
        if 'docker_app_files' in config:
            self._docker_app_files = config['docker_app_files']

        if 'dockerfile_str' in config:
            self._dockerfile_str = config['dockerfile_str']

        if 'dockerfile_file' in config:
            self._dockerfile_file = config['dockerfile_file']

        self._docker_app_cloud_creds_pass_through = None
        if "docker_app_cloud_creds_pass_through" in config:
            self._docker_app_cloud_creds_pass_through = config["docker_app_cloud_creds_pass_through"]

        the_build_context = uid("docker_build_context")
        self._tar_file_name = f"{the_build_context}.tar.gz"
        self._build_context_fp = f"{tempfile.gettempdir()}/{the_build_context}"

    def start(self):
        raise Exception("start() is not implemented")

    def stop(self):
        raise Exception("stop() is not implemented")

    def get_sys_name(self):
        if not self._sys_name:
            raise Exception("sys_name is not set")
        return self._sys_name
    def set_sys_name(self, sys_name):
        self._sys_name = sys_name

    def get_host_name(self):
        if not self._host_name:
            raise Exception("host_name is not set")
        return self._host_name
    def set_host_name(self, host_name):
        self._host_name = host_name

    def get_name(self):
        return self._name

    def get_port(self):
        return self._port

    def get_docker_container_name(self):
        return f"{self.get_sys_name()}-{self.get_name()}_{self.get_port()}"

    def set_docker_network(self, network):
        self._network = network

    def get_docker_network(self):
        return self._network

    @emitter()
    def docker_build(self, image_name, no_cache=False):

        if not os.path.exists(self._build_context_fp):
            print(f"makedirs: {self._build_context_fp}")
            os.makedirs(self._build_context_fp)

        for file in self._docker_app_files:
            self._copy_from(file)

        if self._dockerfile_str:
            the_dockerfile = f"{self._build_context_fp}/Dockerfile"
            print(f"write: {the_dockerfile}")
            with open(the_dockerfile, 'w') as f:
                f.write(self._dockerfile_str)
        elif self._dockerfile_file:
            if not self._copy_from(self._dockerfile_file):
                raise Exception(f"copying {self._dockerfile_file} failed")
        else:
            raise Exception(f"either 'dockerfile_str' or 'dockerfile_file' must be specified")

        cmd = ""
        cmd += f"tar -C {self._build_context_fp} -czf {self._tar_file_name} ."
        self._exec(cmd)

        DockerService.assert_is_running()

        try:
            cmd = ""
            if self._use_buildkit:
                cmd += f"DOCKER_BUILDKIT=1 "
            cmd += f"docker build "
            if no_cache:
                cmd += "--no-cache "
            if self._docker_app_cloud_creds_pass_through == "aws":
                access_key, secret_key = aws.get_credentials()
                cmd += f"--build-arg AWS_ACCESS_KEY_ID={access_key} "
                cmd += f"--build-arg AWS_SECRET_ACCESS_KEY={secret_key} "
            cmd += f"-t {image_name} "
            cmd += f"- < {self._tar_file_name } "
            self._exec(cmd)

        finally:
            cmd = ""
            cmd += f"rm {self._tar_file_name} && rm -rf {self._build_context_fp}"
            self._exec(cmd)

    def docker_run(self, cmd_line=None, env_vars=None):
        cmd = ""
        cmd += f"docker run -d --name {self.get_docker_container_name()} "
        cmd += f"--env RUNTIME_ENV={environment()} "
        cmd += f"--env PYTHONUNBUFFERED=1 "
        if env_vars:
            cmd += f"{env_vars} "
        cmd += self._docker_run_env_dev_aws_keys()
        if self._network:
            cmd += f"--network {self._network.get_name()} "
        for p in self._published_ports:
            cmd += f"--publish {p}:{p} "
        for v_map in self._volume_mappings:
            os.makedirs(v_map[0], exist_ok=True)
            cmd += f"--volume {v_map[0]}:{v_map[1]} "
        cmd += self._docker_run_log_driver()
        cmd += f"--user {self._run_as[0]}:{self._run_as[1]} "
        if self._mem_max:
            cmd += f"--oom-kill-disable --memory={self._mem_max} "
        if self._mem_res:
            cmd += f"--memory-reservation={self._mem_res} "
        if self._swap_max:
            cmd += f"--memory-swap={self._swap_max} "
        cmd += f"{self._image_name} "
        if cmd_line:
            cmd += f"{cmd_line} "
        return self._exec(cmd)

    def docker_stop(self):
        cmd = ""
        cmd += f"docker rm --force {self.get_docker_container_name()} "
        return self._exec(cmd)

    def _docker_run_log_driver(self):
        cmd = ""
        # use the aws log driver in Test and Live so the logs go to Cloudwatch
        if not is_dev_environment():
            log_group = f"{self.get_sys_name()}/{environment()}/{self.get_host_name()}"
            if not log_group.startswith("/"):
                log_group = "/" + log_group
            if log_group.endswith("/"):
                log_group = log_group[:-1]
            cmd += f"--log-driver=awslogs "
            cmd += f"--log-opt awslogs-group={log_group} --log-opt awslogs-create-group=true "
            cmd += f"--log-opt awslogs-stream={self.get_docker_container_name()} "
        return cmd

    def _docker_run_env_dev_aws_keys(self):
        cmd = ""
        # in the Dev environment_name expect AWS keys must be set in the system environment_name
        if is_dev_environment():
            cmd += f"--env AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID "
            cmd += f"--env AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY "
        return cmd

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

    def _exec(self, cmd):
        return exec_cmd(cmd, no_sudo=is_dev_environment(), return_tuple=True)


class DockerSystem:
    def __init__(self, name: str, apps: list[DockerBase] = None ):
        self._name = name
        self._network = DockerNetwork(f"{name}-net", DockerNetwork.DEFAULT_DRIVER)
        self._apps = []
        if apps is None:
            apps = []

        # host connectivity
        self._host_name = socket.gethostname()
        self._host_ip = socket.gethostbyname(self._host_name)

        for app in apps:
            self.add_app(app)

    def set_network_driver(self, driver):
        self._network.set_driver(driver)

    def add_app(self, app: DockerBase):
        app.set_sys_name(self._name)
        app.set_host_name(self._host_name)
        app.set_docker_network(self._network)
        self._apps.append(app)

    def start(self):
        self._network.create()
        nfo = {
            "name": self._name,
            "host": {
                "name": self._host_name,
                "ip": self._host_ip
            }
        }
        for app in self._apps:
            app.start()
            nfo[app.get_name()] = app.get_port()
        return nfo

    def stop(self):
        for app in self._apps:
            app.stop()
        self._network.destroy()

