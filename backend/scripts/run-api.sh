#!/bin/sh
set -eu
cd /home/agent/backend
exec .venv/bin/python -m kiln_api
