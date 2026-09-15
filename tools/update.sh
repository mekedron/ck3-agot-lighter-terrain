#!/usr/bin/env bash
# After an AGOT update: rebuild the textures from the installed AGOT if anything changed,
# then install into the Proton prefix. Safe to run any time; does nothing when up to date.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if python3 tools/make_micro.py --check-only; then
    echo "Up to date with the installed AGOT."
else
    python3 tools/make_micro.py --threads "$(nproc)"
fi
./install.sh
