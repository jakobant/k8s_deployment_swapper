#!/bin/bash
EXEC_PATH=$(dirname "$0")
source $EXEC_PATH/envs.sh

err_report() {
    docker stop openvpn
    docker rm --force openvpn
}

trap err_report ERR
set -e


docker run -it  --name openvpn -p 1194:1194 --cap-add=NET_ADMIN -d $REPO/$NAME:$TAG

sleep 100
docker stop redis
docker rm --force redis

