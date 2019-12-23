#!/usr/bin/env python3

"""Deployment Swap tool

Usage:
  swap_deployment.py swap --deployment=<deployment> [--destination=<remote_host>] [--http_port=<remote_http_port>] [--grpc_port=<remote_grpc_port>] [--disable_readiness] [--no_sidecar]
  swap_deployment.py swap-off --deployment=<deployment>
  swap_deployment.py vpn --deployment=<deployment>
  swap_deployment.py get-swap-env --deployment=<deployment> [--export]
  swap_deployment.py get-env --deployment=<deployment> [--export]
  swap_deployment.py setup-sudoers
  swap_deployment.py reset-vpn
  swap_deployment.py (-h | --help)

Options:
  -h --help     Show this screen.
"""

from docopt import docopt
import sys
import os

sys.path.append(os.path.abspath(__file__))
from deployment_swapper import SwapDeployment


def main():
    args = docopt(__doc__)
    if args['swap']:
        deployment = args['--deployment']
        remote_host = args['--destination']
        http_port = args['--http_port']
        grpc_port = args['--grpc_port']
        readiness = args['--disable_readiness']
        sidecar =  args['--no_sidecar']
        swap = SwapDeployment(deployment, remote_host, http_port, grpc_port)
        swap.create_configmap(swap.create_configmaps_objects())
        new_deployment, curr_deployment = swap.generate_deployment_swap(
            disable_readiness=readiness,
            skip_openvpn_sidecar=sidecar
        )
        swap.create_deployment(new_deployment)
        swap.scale_deployment(curr_deployment, replicas=0)

    if args['swap-off']:
        deployment = args['--deployment']
        swap = SwapDeployment(deployment, None, None, None)
        swap_deployment, curr_deployment = swap.get_swap_deployment()
        swap.scale_deployment(curr_deployment, replicas=1)
        swap.delete_deployment(swap_deployment)

    if args['vpn']:
        deployment = args['--deployment']
        swap = SwapDeployment(deployment, None, None, None)
        swap_deployment, curr_deployment = swap.get_swap_deployment()
        swap.portforward_openvpn(swap_deployment)

    if args['get-env']:
        deployment = args['--deployment']
        export = args['--export']
        swap = SwapDeployment(deployment, None, None, None)
        run_deployment = swap.get_deployment("{}".format(deployment))
        swap.get_env_values(run_deployment, export)

    if args['get-swap-env']:
        deployment = args['--deployment']
        export = args['--export']
        swap = SwapDeployment(deployment, None, None, None)
        swap_deployment, run_deployment = swap.get_swap_deployment()
        swap.get_env_values(swap_deployment, export)

    if args['setup-sudoers']:
        swap = SwapDeployment("dummy", None, None, None)
        swap.setup_sudoers()

    if args['reset-vpn']:
        swap = SwapDeployment("dummy", None, None, None)
        swap.reset_vpn()


if __name__ == '__main__':
    main()
