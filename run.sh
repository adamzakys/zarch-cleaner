#!/bin/sh
# Jalankan Zarch Cleaner langsung dari kode sumber (tanpa install).
set -eu

HERE="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
exec env PYTHONPATH="$HERE${PYTHONPATH:+:$PYTHONPATH}" python3 -m zarchcleaner "$@"
