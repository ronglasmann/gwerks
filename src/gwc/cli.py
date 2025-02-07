import getopt
import signal
import sys

# --------------------------------------------------------------------------- #
# Command Line Interface (cli) support
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Parse command line into a dict; handle keyboard interrupts (sigterm)
def cli(opts_list):

    signal.signal(signal.SIGTERM, _handle_sigterm)

    # initialize valid options and specified arguments
    unx_opts, gnu_opts, arg_tpls = _unx_gnu_tpls(opts_list)

    # command line args
    args = sys.argv[1:]

    results = {}

    # parse command line
    arguments, values = getopt.getopt(args, unx_opts, gnu_opts)

    # evaluate given options
    for current_arg, current_value in arguments:
        for arg_tpl in arg_tpls:
            if current_arg in arg_tpl:
                results[arg_tpl[1][2:]] = current_value
                break

    return results


# --------------------------------------------------------------------------- #
# translate a list of option names to unix and gnu command line options
def _unx_gnu_tpls(opts_list):
    u_opts = ""
    g_opts = []
    tpls = []
    for opt in opts_list:

        # gnu_opts
        g_opts.append(f"{opt}=")

        # unx_opts
        u_opt = None
        p = 0
        while u_opt is None:
            u_opt = f"{opt[p:1]}:"
            if u_opt not in u_opts:
                u_opts += u_opt
            else:
                p += 1
                u_opt = None

        tpls.append((f"-{u_opt[:1]}", f"--{opt}"))

    return u_opts, g_opts, tpls


# --------------------------------------------------------------------------- #
# handle keyboard interrupts for a cli
def _handle_sigterm(*args):
    print(f"Received SIGTERM")
    raise KeyboardInterrupt()
