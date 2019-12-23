#!/bin/bash

echo $OVPN_CA | base64 -d > $OPENVPN/ca.crt
echo $OVPN_SERVER | base64 -d > $OPENVPN/server.crt
echo $OVPN_KEY | base64 -d > $OPENVPN/server.key
echo $OVPN_DH | base64 -d > $OPENVPN/dh2048.pem
echo $OVPN_CRL | base64 -d > $OPENVPN/ca.crl
echo $OVPN_TA | base64 -d > $OPENVPN/ta.key

cat > $OPENVPN/server.conf <<EOF
tls-server
cipher AES-256-CBC
reneg-sec 0
duplicate-cn
ca     $OPENVPN/ca.crt
cert   $OPENVPN/server.crt
key    $OPENVPN/server.key
dh     $OPENVPN/dh2048.pem
crl-verify   $OPENVPN/ca.crl
#tls-auth $OPENVPN/ta.key
server $OSERVER_IP_RANGE $OSERVER_MASK
port $OSERVER_PORT

key-direction 0
keepalive 10 40
persist-key
persist-tun
proto $OPENVPN_PROTO
dev tun
management 0.0.0.0 5555
verb 4
OVPN_K8S_SEARCH
push "dhcp-option DNS OVPN_K8S_DNS"

EOF

cidr2mask()
{
    local i
    local subnetmask=""
    local cidr=${1#*/}
    local full_octets=$(($cidr/8))
    local partial_octet=$(($cidr%8))

    for ((i=0;i<4;i+=1)); do
        if [ $i -lt $full_octets ]; then
            subnetmask+=255
        elif [ $i -eq $full_octets ]; then
            subnetmask+=$((256 - 2**(8-$partial_octet)))
        else
            subnetmask+=0
        fi
        [ $i -lt 3 ] && subnetmask+=.
    done
    echo $subnetmask
}

getroute() {
    echo ${1%/*} $(cidr2mask $1)
}

DNS=$(cat /etc/resolv.conf | grep -v '^#' | grep nameserver | awk '{print $2}')
SEARCH=$(cat /etc/resolv.conf | grep -v '^#' | grep search | awk '{$1=""; print $0}')
FORMATTED_SEARCH=""
for DOMAIN in $SEARCH; do
  FORMATTED_SEARCH="${FORMATTED_SEARCH}push \"dhcp-option DOMAIN-SEARCH ${DOMAIN}\"\n"
done
sed 's|OVPN_K8S_SEARCH|'"${FORMATTED_SEARCH}"'|' -i /etc/openvpn/server.conf
sed 's|OVPN_K8S_DNS|'"${DNS}"'|' -i /etc/openvpn/server.conf

for a in ${OVPN_ROUTES}
do
  echo "push \"route $(getroute $a)\"" >> $OPENVPN/server.conf
done

OVPN_SERVER=$OSERVER_IP_RANGE/$OSERVER_MASK
mkdir -p /dev/net
mknod /dev/net/tun c 10 200
[ -z "$OVPN_NATDEVICE" ] && OVPN_NATDEVICE=eth0
iptables -t nat -C POSTROUTING -s $OVPN_SERVER -o $OVPN_NATDEVICE -j MASQUERADE || {
      iptables -t nat -A POSTROUTING -s $OVPN_SERVER -o $OVPN_NATDEVICE -j MASQUERADE
    }
for i in "${OVPN_ROUTES[@]}"; do
  iptables -t nat -C POSTROUTING -s "$i" -o $OVPN_NATDEVICE -j MASQUERADE || {
          iptables -t nat -A POSTROUTING -s "$i" -o $OVPN_NATDEVICE -j MASQUERADE
        }
done

#sysctl -a |grep forward
openvpn $OPENVPN/server.conf