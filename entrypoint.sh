#!/bin/sh
set -eu

HOMELAB_CA="/usr/local/share/ca-certificates/homelab-ca.crt"

if [ -f "$HOMELAB_CA" ]; then
  cat /etc/ssl/certs/ca-certificates.crt "$HOMELAB_CA" > /tmp/ca-bundle.crt
  export REQUESTS_CA_BUNDLE=/tmp/ca-bundle.crt
fi

exec python3 app.py
