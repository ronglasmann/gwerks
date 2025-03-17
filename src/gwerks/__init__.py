"""'Lightweight python modules useful in most projects'"""
import os
from datetime import datetime
import urllib.error
import urllib.request
import urllib.parse

from gwerks.decorators import emitter
from gwerks.shortuuid import ShortUUID


from gwerks.packaging import get_version
__version__ = get_version(__file__)


# --------------------------------------------------------------------------- #
# Server Environments, Regions and Profiles support
# --------------------------------------------------------------------------- #

ENV_KEY = "RUNTIME_ENV"
ENV_DEV = "Dev"
ENV_TEST = "Test"
ENV_LIVE = "Live"
ENV_LIST = [ENV_DEV, ENV_TEST, ENV_LIVE]

REG_KEY = "RUNTIME_REG"
REG_ONE = "us-east-1"
REG_TWO = "us-east-2"
REG_LIST = [REG_ONE, REG_TWO]

PRO_KEY = "AWS_PROFILE"
PRO_DEFAULT = "default"


def is_dev_environment():
    return environment() == ENV_DEV


def is_test_environment():
    return environment() == ENV_TEST


def is_live_environment():
    return environment() == ENV_LIVE


def change_to_dev_environment():
    change_environment(ENV_DEV)


def change_to_test_environment():
    change_environment(ENV_TEST)


def change_to_live_environment():
    change_environment(ENV_LIVE)


@emitter()
def change_environment(env):
    if env not in ENV_LIST:
        raise Exception(f"Unsupported environment: {env}")
    os.environ[ENV_KEY] = env
    print(f"You are now working in the **> {environment()} <** environment.")


def environment():
    if ENV_KEY not in os.environ:
        os.environ[ENV_KEY] = ENV_DEV
    env = os.environ[ENV_KEY]
    if env not in ENV_LIST:
        raise Exception(f"Unsupported environment: {env}")
    return env


def region():
    if REG_KEY not in os.environ:
        os.environ[REG_KEY] = REG_ONE
    reg = os.environ[REG_KEY]
    if reg not in REG_LIST:
        raise Exception(f"Unsupported region: {reg}")
    return reg


def profile(new_profile=None):
    if PRO_KEY not in os.environ:
        os.environ[PRO_KEY] = PRO_DEFAULT
    if new_profile is not None:
        os.environ[PRO_KEY] = new_profile
    prf = os.environ[PRO_KEY]
    return prf


# --------------------------------------------------------------------------- #
# Datetime formatting functions
# --------------------------------------------------------------------------- #

DATETIME_FORMAT = "%m/%d/%Y %I:%M:%S %p"
DATETIME_FORMAT_W_MS = f"%Y-%m-%d %H:%M:%S.%f"
DATE_FORMAT = "%m/%d/%Y"
TIME_FORMAT = "%I:%M:%S %p"


def now():
    """Short convenience method for the current time"""
    return datetime.now()


def fnow():
    n = now().strftime(DATETIME_FORMAT)
    return n


def fnow_w_ms():
    """Returns current time as a formatted string"""
    return now().strftime(DATETIME_FORMAT_W_MS)


def fnow_date():
    n = now().strftime(DATE_FORMAT)
    return n


def fnow_time():
    n = now().strftime(TIME_FORMAT)
    return n


# --------------------------------------------------------------------------- #
# HTTP requests
# --------------------------------------------------------------------------- #

@emitter()
def http_post(url, data=None, headers=None):

    if data is None:
        data = {}
    if headers is None:
        headers = {}

    if 'Content-Type' not in headers:
        headers['Content-Type'] = 'application/x-www-form-urlencoded'

    print(f"{url} data: {data} headers: {headers}")

    # data_encoded = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method='POST')

    try:
        response_data = urllib.request.urlopen(req).read().decode('utf-8')
        print(f"SUCCESS: {response_data}")
        return response_data
    except urllib.error.HTTPError as e:
        error_info = e.read().decode('utf-8')
        print(f"ERROR: {e.code} {e.reason} {error_info}")
        return error_info


@emitter()
def http_get(url, headers=None):

    if headers is None:
        headers = {}

    print(f"{url} headers: {headers}")
    req = urllib.request.Request(url, headers=headers, method='GET')

    with urllib.request.urlopen(req) as response:
        response_data = response.read().decode('utf-8')

    print(f"SUCCESS: {response_data}")
    return response_data


def uid(namespace=None, length=None):
    the_uid = ShortUUID().uuid(namespace, length)
    return the_uid
