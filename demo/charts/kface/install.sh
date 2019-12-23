#!/usr/bin/env bash

EXEC_PATH=$(dirname "$0")


helm template $EXEC_PATH \
--name kface \
$@| kubectl create -f -
