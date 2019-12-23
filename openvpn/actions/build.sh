#!/bin/bash
set -e

EXEC_PATH=$(dirname "$0")
source $EXEC_PATH/envs.sh

docker build  --tag $REPO/$NAME:$TAG .

