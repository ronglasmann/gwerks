import os
import traceback
from time import time
from datetime import datetime
from .cli import cli
from .messaging import slack_send_msg

UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# CLI entry point for setting a package version
#   -p, --package_dir - path to the directory containing a python package, required
#   -b, --build_num   - build number to apply to the version string, required
def cli_set_version():
    try:
        opt_map = cli(["package_dir", "build_num"])

        package_dir = opt_map.get("package_dir")
        if package_dir is None:
            raise Exception(f"package_dir is None, unable to set version")
        build_num = opt_map.get("build_num")
        if build_num is None:
            raise Exception(f"build_num is None, unable to set version")

        print(set_version(package_dir, build_num))

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        exit(1)


# --------------------------------------------------------------------------- #
# CLI entry point for getting a package version
#   -p, --package_dir - path to the directory containing a python package, required
def cli_get_version():
    try:
        opt_map = cli(["package_dir"])

        package_dir = opt_map.get("package_dir")
        if package_dir is None:
            raise Exception(f"package_dir is None, unable to get version")

        print(get_version(package_dir))

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        exit(1)


# --------------------------------------------------------------------------- #
# CLI entry point for sending a package version to Slack
#   -p, --package_dir - path to the directory containing a python package, required
#   -c, --channel     - Slack channel to message, required
def cli_notify_version():
    try:
        opt_map = cli(["package_dir", "channel", "auth_token"])

        package_dir = opt_map.get("package_dir")
        if package_dir is None:
            raise Exception(f"package_dir is None, unable to notify version")
        channel = opt_map.get("channel")
        if channel is None:
            raise Exception(f"channel is None, unable to notify version")
        auth_token = opt_map.get("auth_token")
        if auth_token is None:
            raise Exception(f"auth_token is None, unable to notify version")

        notify_version(package_dir, channel, auth_token)

    except Exception as e:
        print(f"ERROR: {e}")
        traceback.print_exc()
        exit(1)


# --------------------------------------------------------------------------- #
# send version to Slack
def notify_version(pkg_dir, channel, auth_token):
    try:

        # Get version
        version = get_version(pkg_dir)
        slack_send_msg(channel, f"{pkg_dir}: *{version}*", auth_token)

    except Exception as ex:
        msg = f"ERROR getting version for {pkg_dir}: {ex}"
        slack_send_msg(channel, msg, auth_token)
        raise Exception(msg)


# --------------------------------------------------------------------------- #
# creates a version file and returns the version string that it contains
def set_version(pkg_dir, build_number=None):
    if build_number is None:
        build_number = _make_build_number()
    the_v_file = _get_version_file_path(pkg_dir)
    version_string = _make_version_string(build_number)
    with open(the_v_file, "w") as f:
        f.write(version_string)
    # print(f"{pkg_dir}: {version_string}")
    return version_string


# --------------------------------------------------------------------------- #
# get the current version, looks for the version file first
def get_version(pkg_dir):
    the_v_file = _get_version_file_path(pkg_dir)
    if not os.path.exists(the_v_file):
        # set_version(pkg_dir)
        version_string = _make_version_string()
    else:
        with open(the_v_file, "r") as f:
            version_string = f.read()

    return version_string


# --------------------------------------------------------------------------- #
# get the file path for the version file if it exists
def _get_version_file_path(pkg_dir):
    the_version_filename = "version.txt"
    # the_dir = os.path.dirname(os.path.realpath(pkg_dir))
    the_dir = os.path.dirname(pkg_dir)
    if not os.path.exists(the_dir):
        raise Exception(f"Package not found: {the_dir}")
    the_v_file = os.path.join(the_dir, the_version_filename)
    return the_v_file


# --------------------------------------------------------------------------- #
# returns a build number for dev builds
def _make_build_number():
    return f"{int(time())}"


# --------------------------------------------------------------------------- #
# returns a version string: YYYY.MM.<build_number>
def _make_version_string(build_number=None):
    if build_number is None:
        build_number = _make_build_number()
    return f'{datetime.now().strftime("%Y.%m")}.{build_number}'
