import getopt
import signal
import sys
from collections import UserDict
from gwerks.decorators import emitter

# --------------------------------------------------------------------------- #
# Command Line Interface (cli) support
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Parse command line into a dict; handle keyboard interrupts (sigterm)
def cli(opts_map_list: list[dict]):

    signal.signal(signal.SIGTERM, _handle_sigterm)

    # initialize valid options and specified arguments
    unx_opts, gnu_opts, arg_tpls, clo = _unx_gnu_tpls(opts_map_list)

    # command line args
    args = sys.argv[1:]

    # parse command line
    arguments, values = getopt.getopt(args, unx_opts, gnu_opts)

    # evaluate given options
    for current_arg, current_value in arguments:
        for arg_tpl in arg_tpls:
            if current_arg in arg_tpl:
                clo[arg_tpl[1][2:]] = current_value
                break

    return clo


class Clo(UserDict):

    REQUIRED = "***required***"

    @emitter(override_func_name="clo")
    def __getitem__(self, key):
        value = super().__getitem__(key)
        if value == Clo.REQUIRED:
            raise Exception(f"'{key}' must be specified")
        if value:
            print(f"{key}: {value}")
        return value


# --------------------------------------------------------------------------- #
# translate a list of option names to unix and gnu command line options
def _unx_gnu_tpls(opts_map_list: list[dict]) -> tuple[str, list[str], list[tuple[str, str]], Clo]:
    u_opts = ""
    g_opts = []
    tpls = []
    defaults_clo = Clo()
    for opt_map in opts_map_list:
        # print(f"opt_map: {opt_map}")

        for opt, default in opt_map.items():

            # gnu_opts
            g_opts.append(f"{opt}=")

            # unx_opts
            u_opt = ""
            opt_s = opt.split("_")
            for o in opt_s:
                u_opt += o[:1]
            u_opt += ":"
            if ":" + u_opt in ":" + u_opts:
                raise Exception(f"abbreviation for {opt} ({u_opt}) already exists ({u_opts}), "
                                f"unable to configure command line")
            else:
                u_opts += u_opt

            tpls.append((f"-{u_opt[:1]}", f"--{opt}"))
            defaults_clo[opt] = default

    return u_opts, g_opts, tpls, defaults_clo


# --------------------------------------------------------------------------- #
# handle keyboard interrupts for a cli
def _handle_sigterm(*args):
    print(f"Received SIGTERM")
    raise KeyboardInterrupt()
