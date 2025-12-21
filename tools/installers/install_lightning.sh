#!/usr/bin/env bash

set -euo pipefail

if [ $# != 0 ]; then
    echo "Usage: $0"
    exit 1;
fi

if ! python -c "import packaging.version" &> /dev/null; then
    python3 -m pip install packaging
fi

python3 -m pip install lightning

# Check the pytorch version is not changed from the original version
current_torch_version="$(python3 -c 'import torch; print(torch.__version__)')"
if [ ${torch_version} != "${current_torch_version}" ]; then
    echo "[ERROR] The torch version has been changed. Please report to espnet developers"
    exit 1
fi
