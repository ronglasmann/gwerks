import os
from datetime import datetime
from time import time
from gwerks.commands import execute_cmd


def get_version(pkg_root_file_path):
    pkg = Package(pkg_root_file_path)
    return pkg.get_version()


class VCS:
    def __init__(self):
        pass

    def release_create(self, version):
        raise Exception('not implemented')


class Package:
    VERSION_FILE_NAME = "version.txt"

    def __init__(self, path_to_pkg):
        the_dir = os.path.dirname(path_to_pkg)
        if not os.path.exists(the_dir):
            raise Exception(f"Package not found: {the_dir}")
        self._version_file_path = os.path.join(the_dir, Package.VERSION_FILE_NAME)

    def release(self, vcs: VCS, release_branch="main"):

        # commit and push the version file
        version = self.get_version()
        execute_cmd(f"git add {self._version_file_path}", raise_exc=False)
        execute_cmd(f"git commit -m 'version {version}' {self._version_file_path}", raise_exc=False)
        execute_cmd(f"git push origin {release_branch}", raise_exc=False)

        # create the release
        vcs.release_create(self.get_version())

        # set the next version
        self._increment_version()

    def get_version(self):
        if not os.path.exists(self._version_file_path):
            version_string = self._increment_version_string(None)
        else:
            with open(self._version_file_path, "r") as f:
                version_string = f.read()
        return version_string

    def _increment_version(self):
        current_version = self.get_version()
        new_version = self._increment_version_string(current_version)
        with open(self._version_file_path, "w") as f:
            f.write(new_version)
        return new_version

    def _increment_version_string(self, v_str: str = None):
        if v_str is None:
            return f'{datetime.now().strftime("%y.%-m")}.0.{int(time())}'
        v_parts = v_str.split(".")
        b_num = int(v_parts[2]) + 1
        return f'{datetime.now().strftime("%y.%-m")}.{b_num}'

