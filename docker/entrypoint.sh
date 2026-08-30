#!/bin/sh
# AUT-1533 (AB-SEC): generic entrypoint — load *_FILE secrets, then exec CMD.
. /usr/local/bin/lib-load-secrets.sh
exec "$@"
