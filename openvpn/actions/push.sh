#!/bin/bash
set -e

EXEC_PATH=$(dirname "$0")
source $EXEC_PATH/envs.sh

docker push $REPO/$NAME:$TAG

