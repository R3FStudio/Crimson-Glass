#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
if git rev-parse --verify '@{upstream}' >/dev/null 2>&1; then
    git pull --ff-only
fi
exec sh ./install.sh "$@"
