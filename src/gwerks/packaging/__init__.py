import os
from datetime import datetime
from time import time


def _get_version_file_path(pkg_dir):
    the_version_filename = "version.txt"
    # the_dir = os.path.dirname(os.path.realpath(pkg_dir))
    the_dir = os.path.dirname(pkg_dir)
    if not os.path.exists(the_dir):
        raise Exception(f"Package not found: {the_dir}")
    the_v_file = os.path.join(the_dir, the_version_filename)
    return the_v_file


def _make_sandbox_build_number():
    return f"0.{int(time())}+SANDBOX"


def _make_version_string(build_number=None):
    if build_number is None:
        build_number = _make_sandbox_build_number()
    return f'{datetime.now().strftime("%Y.%m")}.{build_number}'


def set_version(pkg_dir, build_number=None):
    if build_number is None:
        build_number = _make_sandbox_build_number()
    the_v_file = _get_version_file_path(pkg_dir)
    version_string = _make_version_string(build_number)
    with open(the_v_file, "w") as f:
        f.write(version_string)
    # print(f"{pkg_dir}: {version_string}")
    return version_string


def get_version(pkg_dir):
    the_v_file = _get_version_file_path(pkg_dir)
    if not os.path.exists(the_v_file):
        # set_version(pkg_dir)
        version_string = _make_version_string()
    else:
        with open(the_v_file, "r") as f:
            version_string = f.read()

    return version_string
