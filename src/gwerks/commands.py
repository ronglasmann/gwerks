import os
import subprocess


# --------------------------------------------------------------------------- #
# execute system commands and return output, optionally raise Exceptions
# on non-zero exit codes
def _run_subprocess(cmd, raise_exc=True, no_sudo=True):
    cmd = f"{sudo(no_sudo)} {cmd}"
    print(f"COMMAND: {cmd}")

    # Execute the 'ls -l' command and capture the output
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)

    exit_code = result.returncode
    if raise_exc and exit_code != 0:
        error_msg = f"ERROR: [{exit_code}]"
        if result.stderr:
            error_msg += f" {result.stderr}"
        print(error_msg)
        raise Exception(error_msg)

    # Print the standard output and return code
    result_msg = f"SUCCESS: [{result.returncode}]"
    if result.stdout:
        result_msg += f" {result.stdout}"

    # Print the standard error, if any
    if result.stderr:
        result_msg += f" {result.stderr}"

    # Print the return code
    print(result_msg)
    return result.stdout


# --------------------------------------------------------------------------- #
# execute system commands, optionally raise Exceptions on non-zero exit codes
def execute_cmd(cmd, raise_exc=True, no_sudo=True):
    return _run_subprocess(cmd, raise_exc=raise_exc, no_sudo=no_sudo)
    # cmd = f"{sudo(no_sudo)} {cmd}"
    # print(f"COMMAND: {cmd}")
    # exit_code = os.system(cmd)
    # if raise_exc and exit_code != 0:
    #     error_msg = f"ERROR: [{exit_code}]"
    #     print(error_msg)
    #     raise Exception(error_msg)
    # print(f"SUCCESS: [{exit_code}]")
    # return exit_code


# --------------------------------------------------------------------------- #
# run commands as root outside the Dev environment_name
def sudo(no_sudo=True):
    if no_sudo:
        return ""
    return "sudo"
