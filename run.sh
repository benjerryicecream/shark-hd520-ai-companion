#!/bin/sh
# Start the HD520 companion REST server on localhost only.
cd "$(dirname "$0")"
exec python3 server.py
