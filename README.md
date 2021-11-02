
# K8S swap deployment
Tools to swap out a deployment so that local debugging would be possible.  Uses Openvpn with ```kubectl port-forward```

## How does  it work?

![Overview Diagram](https://github.com/jakobant/k8s_deployment_swapper/raw/master/demo/swap_deployment.png)


## Command line
```
swap_deployment.py
  swap_deployment.py swap --deployment=<deployment> [--destination=<remote_host>] [--http_port=<remote_http_port>] [--grpc_port=<remote_grpc_port>] [--disable_readiness] [--no_sidecar]
  swap_deployment.py swap-off --deployment=<deployment>
  swap_deployment.py vpn --deployment=<deployment>
  swap_deployment.py get-swap-env --deployment=<deployment> [--export]
  swap_deployment.py get-env --deployment=<deployment> [--export]
  swap_deployment.py setup-sudoers
  swap_deployment.py reset-vpn
```
### swap_deployment.py swap --deployment=\<deployment>
Swap a deployment out with nginx forwarder and opepnvpn sidecar
- --deployment=\<deployment>
    * The deployment you want to swap out
- [--destination=\<remote_host>]
    * Default the the nginx proxy config will forward the traffic to you local openvpn client
    ip address (192.168.88.6), but you can override that with any address.
- [--http_port=\<remote_http_port>]
    * Override the default http port in nginx configs
- [--grpc_port=\<remote_grpc_port>]
    * Override the default grpc port in nginx configs
- [--disable_readiness]
    * Disable rediness setting for the swapped deployment

### swap_deployment.py swap-off --deployment=\<deployment>
Clear the swapped deployment

### swap_deployment.py vpn --deployment=\<deployment>
Open vpn connection to the swapped deployment. This will open two new terminals.
- One terminal will run the ```kubectl port-forward```command for Openvpn client
- One terminal will run the openvpn client connection to the pod sidecar

### swap_deployment.py get-env --deployment=\<deployment>
Connect to the swapped out pods and get the environment variables values
- [--export]
    * Get the env values with export... ```export REDIS=1.2.3.4```

### swap_deployment.py setup-sudoers
The openvpn client connection does require sudoers to connect. The setup-sodoers
will create a NOPASSWD sudoers config for the openvpn command. Run this if you do
not want to type in the sudoers password every time openvpn is started.

### swap_deployment.py reset-vpn
This will close the vpn connection correctly, this caa also fix network
DNS network issues that can raise if you do not close the openvpn client
connection correctly.
- I can leave you computer in the state where is using DNS server from k8s
cluster with out a openvpn connection. That will be a problem.

## Demo
Simple demo: Deploy [Simple Flask face_recognition](https://github.com/jakobant/kface)
to Google Kubernets.
- Clone k8s_deployment_swapper
- Clone kface
- Install the demo
- Update settings.ini to match the cluster pods and service network
- Swap a deployment
- Connect to the Openvpn sidecar
- Connect to the remote redis ```nc kface-redis 6379```
- Run the deployment locally and get the traffic from k8s

<a href="http://www.youtube.com/watch?feature=player_embedded&v=4EPR__KXGvo" target="_blank"><img src="http://img.youtube.com/vi/4EPR__KXGvo/0.jpg"
alt="Deployment Swap Video" width="480" height="360" border="1" /></a>

### The demo steps
Clone k8s_deployment_swapper and install the demo
```
git clone https://github.com/jakobant/k8s_deployment_swapper.git
cd k8s_deployment_swapper
./demo/charts/kface/install.sh
```
Get the deployment, pods and the ingress service
```
kubectl get pods
kubectl get ingress
kubectl describe  ingress
kubectl get ingress -o jsonpath={.items[0].status.loadBalancer.ingress[].ip}
```
Clone the kface an install some demo data
```
git clone https://github.com/jakobant/kface.git
cd kface
curl -XPOST -Fname='Barak Obama' -Ffile=@test/obama.jpg http://<google ingress>/upload
curl -XPOST -Ffile=@test/obamaandbiden.jpg http://<google ingress>/who
```
Swap a deployment, opens a kubectl port-forward and VPN connection. Connect to redis running on k8s
```
./swap_deployment.py swap --deployment=kface-upload
./swap_deployment.py vpn --deployment=kface-upload
./swap_deployment.py get-env --deployment=kface-upload
./swap_deployment.py get-env --deployment=kface-upload > ENV_TEST
nc kface-redis 6379
```
Run the kface locally or in your Python Ide like PyCharm.
```
# from kface path
REDIS=kface-redis python ./app.py
# Add Biden and debug from another window.
curl -XPOST -Fname='Biden' -Ffile=@test/biden.jpg http://<google ingress>/upload
curl -XPOST -Ffile=@test/obamaandbiden.jpg http://<google ingress>/who
```

## Appendix for google GKE network information
Get network : pods and service networks
```
gcloud container clusters describe <cluste name> --zone <zone> --project <project>|egrep "clusterIpv4Cidr|servicesIpv4Cidr
clusterIpv4Cidr: 10.4.0.0/14
  clusterIpv4Cidr: 10.4.0.0/14
  clusterIpv4CidrBlock: 10.4.0.0/14
  servicesIpv4Cidr: 10.0.0.0/20
  servicesIpv4CidrBlock: 10.0.0.0/20
servicesIpv4Cidr: 10.0.0.0/20
```
## Appendix for kops network information
```
kops get cluster <cluster -name> -o yaml |grep CIDR
  networkCIDR: 172.38.0.0/16
  nonMasqueradeCIDR: 172.16.0.0/14
```

## Appendix for AWS EKS network information
   -# TODO
