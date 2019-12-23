import copy
import os
import sys
import subprocess
import tempfile
import shutil
import psutil
import stat
import functools
import configparser
from kubernetes import client, config
from kubernetes.client import configuration
from kubernetes.client.rest import ApiException
from kubernetes.stream import stream
from jinja2 import Template


def run_in_new_window(code, hold=False):
    if sys.platform == "darwin":
        with tempfile.NamedTemporaryFile("w+t", delete=False) as start_new:
            start_new.write('tell application "Terminal"\n')
            start_new.write(f'    set w to do script "{code}"\n')
            start_new.write(f"    activate\n")
            if hold:
                start_new.write("    repeat\n")
                start_new.write("        delay 1\n")
                start_new.write("        if not busy of w then exit repeat\n")
                start_new.write("    end repeat\n")
            start_new.write("end tell\n")
            start_new.close()
            proc = subprocess.Popen(
                ["osascript", start_new.name],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
    elif sys.platform == "linux":
        terminal = os.getenv("TERMINAL", shutil.which("xfce4-terminal"))
        if not terminal:
            print("You need to set the TERMINAL env ...")
            print("tilix, gnome-terminal and xfce4-terminal are officially supported")
            print("others might work")
            sys.exit(1)
        hold_args = []
        terminal_args = []
        if hold:
            if os.path.basename(terminal) == "xfce4-terminal":
                hold_args = ["--disable-server"]

        if os.path.basename(terminal) == "tilix":
            terminal_args = ["-a", "session-add-down"]

        with tempfile.NamedTemporaryFile("w+t", delete=False) as start_new:
            start_new.write(code)
            start_new.close()
            args = [
                terminal,
                *terminal_args,
                *hold_args,
                "-e",
                "bash {}".format(start_new.name),
            ]

            proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
    else:
        print("Your platform: {} is not supported!!".format(sys.platfrom))
        sys.exit(1)
    if hold:
        if proc.wait() != 0:
            raise RuntimeError(proc.stderr.read().decode())


class OpenVpn:

    def __init__(self, namespace, env):
        self.namespace = namespace
        self.env = env
        self.run = functools.partial(
            subprocess.run,
            env=env,
            universal_newlines=True,
            capture_output=True,
            check=True,
        )
        self.conf_location = os.path.join(os.getcwd(), "config")
        self.vpn_profile_fn = os.path.join(self.conf_location, "vpn-test.ovpn")
        self.vpn_pid_file = os.path.join(self.conf_location, "vpn.pid")
        self.vpn_updown_script = os.path.join(
            self.conf_location,
            f"update_resolv_conf.{sys.platform}.sh",
        )

    def check_openvpn_installed(self):
        with self.override_env():
            if not shutil.which("openvpn"):
                if sys.platform == "darwin":
                    print("openvpn not installed. brew/apt/pacman install openvpn")
                    print("Hint (for macs):")
                    print("    # Run this")
                    print("    brew install openvpn")
                    print("    # Add this line to ~/.bash_profile")
                    print("    export PATH=$(brew --prefix openvpn)/sbin:$PATH")
                else:
                    print("openvpn not installed. apt install openvpn")
                    print("Hint (for linux):")
                    print("    # Run this")
                    print("    apt install openvpn openresolv")
                    print("    openresolv is also needed!!!")
                sys.exit(1)

    def run_vpn_if_needed(self):
        """Run vpn in new termianl window"""
        vpn_pid = self.get_vpn_pid()
        if vpn_pid:
            print(f"VPN running, pid {vpn_pid}")
        else:
            print("Running openvpn in new window.")
            openvpn_path = shutil.which("openvpn")
            if not openvpn_path:
                raise RuntimeError("openvpn not found in path!")
            run_in_new_window(
                f"sudo {openvpn_path} --config {self.vpn_profile_fn} "
                f"--up {self.vpn_updown_script} --down {self.vpn_updown_script} "
                f"--script-security 3 --writepid {self.vpn_pid_file}\n"
            )

    def get_vpn_pid(self):
        if os.path.isfile(self.vpn_pid_file):
            with open(self.vpn_pid_file, "r") as f:
                pid = int(f.read().strip())
            if psutil.pid_exists(pid):
                return pid

    def kill_vpn(self):
        vpn_pid = self.get_vpn_pid()
        if vpn_pid:
            print("Killing openvpn, will need elevated access...")
            kill_path = shutil.which("kill")
            subprocess.run(["sudo", kill_path, "-2", str(vpn_pid)])
        self.reset_vpn()

    def reset_vpn(self):
        my_env = os.environ
        my_env["script_type"] = "down"
        my_env["dev"] = "none"
        if sys.platform == "linux":
            subprocess.run(["sudo", "cp", "/etc/resolv.conf.bak", "/etc/resolv.conf"])
        else:
            subprocess.run([self.vpn_updown_script], env=my_env)

    def setup_sudoers(self):
        proc = subprocess.run(
            ["sudo", "-n", "-l"],
            check=False,
            capture_output=True,
            universal_newlines=True,
        )
        required_commands = ["openvpn --config", "kill -2"]
        if not all(part in proc.stdout for part in required_commands):
            with tempfile.NamedTemporaryFile("w+t", delete=False) as sudo_config:
                username = os.getenv("USER")
                sudo_config.write(
                    "Cmnd_Alias    OVPN =  {} --config *\n".format(
                        shutil.which("openvpn")
                    )
                )
                sudo_config.write(
                    "Cmnd_Alias    KILL =  {} -2 *\n".format(shutil.which("kill"))
                )
                sudo_config.write(
                    "Cmnd_Alias    NETFIX =  {} /etc/resolv.conf.bak /etc/resolv.conf\n".format(
                        shutil.which("cp")
                    )
                )
                if sys.platform == "darwin":
                    target_sudo_file = f"/etc/sudoers.d/swapper-{username}"
                    sudo_config.write(
                        "%admin          ALL = (ALL) NOPASSWD:OVPN\n"
                        "%admin          ALL = (ALL) NOPASSWD:KILL\n"
                    )
                else:
                    target_sudo_file = f"/etc/sudoers.d/swapper-{username}"
                    sudo_config.write(
                        f"{username}          ALL = (ALL) NOPASSWD:OVPN\n"
                        f"{username}          ALL = (ALL) NOPASSWD:KILL\n"
                        f"{username}          ALL = (ALL) NOPASSWD:NETFIX\n"
                    )
                sudo_config.close()
                print(
                    f"Copying sudo config to {target_sudo_file}, will need elevated access"
                )
                os.chmod(sudo_config.name, stat.S_IRUSR | stat.S_IRGRP)
                run_in_new_window(
                    f"sudo cp {sudo_config.name} {target_sudo_file}", hold=True
                )

    def override_env(self):
        return self.env


class SwapDeployment:
    def __init__(self, deployment_name, remote_host, remote_http_port, remote_grpc_port):
        if deployment_name != "dummy":
            self.config = config.load_kube_config()
        cf = configparser.ConfigParser()
        cf.read('config/settings.ini')
        self.configs = cf['default']
        configuration.assert_hostname = False
        self.extensions_v1beta1 = client.ExtensionsV1beta1Api()
        self.api_inst = client.CoreV1Api()
        self.namespace = self._get_current_namespace()
        self.deployment_name = deployment_name
        if remote_host:
            self.remote_host = remote_host
        else:
            self.remote_host = self.configs['DEFAULT_OVPN_CLIENT_IP']
        if remote_http_port:
            self.remote_http_port = remote_http_port
        else:
            self.remote_http_port = "80"
        if remote_grpc_port:
            self.remote_grpc_port = remote_grpc_port
        else:
            self.remote_grpc_port = "50050"
        self.openvpn =  OpenVpn(self.namespace, os.environ)

    def get_deployment(self, deployment_name):
        try:
            api_response = self.extensions_v1beta1.read_namespaced_deployment(
                deployment_name, self.namespace
            )
        except ApiException as e:
            print("Exception when calling read_namespaced_deployment: %s\n" % e)
            exit(0)
        return api_response

    def _get_current_namespace(self):
        try:
            return config.list_kube_config_contexts()[1]["context"]["namespace"]
        except KeyError:
            return "default"

    def get_default_image(self):
        return self.configs['SWAP_IMAGE']

    def create_deployment(self, deployment):
        try:
            self.extensions_v1beta1.create_namespaced_deployment(
                body=deployment, namespace=self.namespace
            )
        except ApiException as e:
            print("Exception when calling create_namespaced_deployment: %s\n" % e)
            exit(0)

    def deployment_exists(self, deployment):
        deployments = [
            item.metadata.name
            for item in self.extensions_v1beta1.list_namespaced_deployment(
                namespace=self.namespace
            ).items
        ]
        return deployment in deployments

    def get_config_template(self):
        template_file = os.path.join(
            os.getenv("CONF_DIR", "./"), "nginx_template.conf.j2"
        )
        with open(template_file) as file_:
            template = Template(file_.read())
        swap = {
            "remote_host": self.remote_host,
            "service_id": self.deployment_name,
            "remote_http_port": self.remote_http_port,
            "remote_grpc_port": self.remote_grpc_port,
        }
        return template.render(swap)

    def create_configmaps_objects(self):
        metadata = client.V1ObjectMeta(
            name="{}-swap".format(self.deployment_name), namespace=self.namespace
        )
        return client.V1ConfigMap(
            data={"default.conf": self.get_config_template()},
            kind="ConfigMap",
            metadata=metadata,
        )

    def create_configmap(self, obj):
        try:
            self.api_inst.create_namespaced_config_map(
                namespace=self.namespace, body=self.create_configmaps_objects()
            )
        except ApiException:
            self.api_inst.replace_namespaced_config_map(
                namespace=self.namespace,
                name="{}-swap".format(self.deployment_name),
                body=self.create_configmaps_objects(),
            )

    def get_side_car(self):
        """Return the openvpn sidecar"""
        return {
            'name': 'openvpn',
            'image': self.configs['OPENVPN_SIDECAR'],
            'env': [
                {'name': 'OPENVPN_PROTO', 'value': 'tcp'},
                {'name': 'OVPN_ROUTES', 'value': self.configs['DEFAULT_POD_SERVICE']}
            ],
            'ports': [
                {'name': 'openvpn', 'protocol': 'TCP', 'containerPort': 1194},
                {'containerPort': 1194, 'name': 'uovpn', 'protocol': 'UDP'''}
            ],
            'securityContext': {'capabilities': {'add': ['NET_ADMIN']}},
        }

    def set_configmap_volumes(self, original):
        name = "{}-swap".format(self.deployment_name)
        volume = client.V1Volume(
            config_map=client.V1ConfigMapVolumeSource(name=name, default_mode=420),
            name=name,
        )
        volume_mount = client.V1VolumeMount(mount_path="/etc/nginx/conf.d", name=name)
        if not original.spec.template.spec.volumes:
            original.spec.template.spec.volumes = [volume]
        else:
            original.spec.template.spec.volumes.append(volume)
        if not original.spec.template.spec.containers[0].volume_mounts:
            original.spec.template.spec.containers[0].volume_mounts = [volume_mount]
        else:
            original.spec.template.spec.containers[0].volume_mounts.append(volume_mount)

    def generate_deployment_swap(self,
                                 disable_liveness=True,
                                 disable_readiness=False,
                                 skip_openvpn_sidecar=False):
        swap_deployment = self.get_deployment("{}".format(self.deployment_name))
        deployment = copy.deepcopy(swap_deployment)
        self.set_configmap_volumes(swap_deployment)

        swap_deployment.metadata.resource_version = None
        swap_deployment.spec.template.spec.containers[0].args = []
        if disable_liveness:
            swap_deployment.spec.template.spec.containers[0].liveness_probe = None
        if disable_readiness:
            swap_deployment.spec.template.spec.containers[0].readiness_probe = None
        swap_deployment.metadata.name = "{}-swap".format(deployment.metadata.name)
        swap_deployment.metadata.labels["remote_http_port"] = self.remote_http_port
        swap_deployment.metadata.labels["remote_grpc_port"] = self.remote_grpc_port
        swap_deployment.metadata.labels["remote_host"] = self.remote_host
        swap_deployment.spec.template.spec.containers[0].image = self.get_default_image()
        if not skip_openvpn_sidecar:
            swap_deployment.spec.template.spec.containers.append(self.get_side_car())
        return swap_deployment, deployment

    def portforward_openvpn(self, deployment):
        labels = deployment.spec.template.metadata.labels
        label_list = None
        for key in labels:
            label_list = self.add_labels(label_list, "{}={}".format(key, labels[key]))
        pod_name = (
            self.api_inst.list_namespaced_pod(
                namespace=self.namespace, label_selector=label_list
            )
                .items[0]
                .metadata.name
        )
        kubeconfig = os.getenv('KUBECONFIG', None)
        if kubeconfig:
            cmd = f"KUBECONFIG={kubeconfig} kubectl port-forward {pod_name} 1194"
        else:
            cmd = f"kubectl port-forward {pod_name} 1194"
        run_in_new_window(cmd)
        self.openvpn.run_vpn_if_needed()

    def setup_sudoers(self):
        self.openvpn.setup_sudoers()

    def reset_vpn(self):
        self.openvpn.reset_vpn()

    def get_swap_deployment(self):
        original = self.get_deployment("{}".format(self.deployment_name))
        swapped = self.get_deployment("{}-swap".format(self.deployment_name))
        return swapped, original

    def scale_deployment(self, deployment, replicas=1):
        deployment.spec.replicas = replicas
        self.extensions_v1beta1.patch_namespaced_deployment(
            name=deployment.metadata.name, namespace=self.namespace, body=deployment
        )

    def delete_deployment(self, deployment):
        self.extensions_v1beta1.delete_namespaced_deployment(
            name=deployment.metadata.name,
            namespace=self.namespace,
            body=client.V1DeleteOptions(),
        )

    def add_labels(self, labels, label):
        if not labels:
            return "{}".format(label)
        return "{},{}".format(labels, label)

    def get_env_values(self, deployment, export):
        envs = "echo FROM_K8S=yes"
        for env in deployment.spec.template.spec.containers[0].env:
            if export:
                envs = "{}; echo export {}=${}".format(envs, env.name, env.name)
            else:
                envs = "{}; echo {}=${}".format(envs, env.name, env.name)
        command = ["/bin/bash", "-c", envs]
        labels = deployment.spec.template.metadata.labels
        label_list = None
        for key in labels:
            label_list = self.add_labels(label_list ,"{}={}".format(key, labels[key]))
        name = (
            self.api_inst.list_namespaced_pod(
                namespace=self.namespace, label_selector=label_list
            )
            .items[0]
            .metadata.name
        )
        container_name = deployment.spec.template.spec.containers[0].name
        try:
            api_response = stream(
                self.api_inst.connect_get_namespaced_pod_exec,
                name=name,
                namespace=self.namespace,
                command=command,
                container=container_name,
                stderr=True,
                stdin=False,
                stdout=True,
                tty=False,
            )
            print(api_response)
        except ApiException as e:
            print(
                "Exception when calling CoreV1Api->connect_get_namespaced_pod_exec: %s\n"
                % e
            )
