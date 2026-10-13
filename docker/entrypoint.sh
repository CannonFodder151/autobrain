#!/bin/sh
# AUT-1533 (AB-SEC): generic entrypoint — preflight secrets perms
# (AUT-5134), load *_FILE secrets, then exec CMD.
# The preflight runs first so a lost read/traverse perm on the
# bind-mounted secrets dir exits 1 with one actionable line before
# anything `cat`s a secret (that loop was the AUT-5125 outage).
/usr/local/bin/preflight-secrets.sh || exit $?
. /usr/local/bin/lib-load-secrets.sh
exec "$@"
