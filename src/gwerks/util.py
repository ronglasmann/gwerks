import subprocess

from gwerks import emitter


class Colors:
    # terminal colors
    blk = "\033[0;90m"
    red = "\033[0;91m"
    grn = "\033[0;92m"
    ylw = "\033[0;93m"
    blu = "\033[0;94m"
    mag = "\033[0;95m"
    cyn = "\033[0;96m"
    whi = "\033[0;97m"
    end = "\033[0m"


# --------------------------------------------------------------------------- #
# helper function for optionally running system commands as root
def sudo(no_sudo=True):
    if no_sudo:
        return ""
    return "sudo"


# --------------------------------------------------------------------------- #
# execute system commands, optionally raise Exceptions on non-zero exit codes
@emitter()
def exec_cmd(cmd, raise_exc=True, no_sudo=True, send_to_stdin=None):
    cmd = f"{sudo(no_sudo)} {cmd}".strip()
    print(cmd)

    # Execute the 'ls -l' command and capture the output
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True, input=send_to_stdin)

    exit_code = result.returncode
    if raise_exc and exit_code != 0:
        error_msg = f"ERROR: [{exit_code}]"
        if result.stderr:
            error_msg += f" {result.stderr}"
        print(error_msg)
        raise Exception(error_msg)

    # Print the standard output and return code
    # result_msg = f"[{result.returncode}] <- {cmd}"
    # if result.stdout:
    #     result_msg += f" {result.stdout}"

    # Print the standard error, if any
    # if result.stderr:
    #     result_msg += f" {result.stderr}"

    # Print the return code
    # print(result_msg)
    return result
