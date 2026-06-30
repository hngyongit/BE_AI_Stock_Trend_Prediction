#!/usr/bin/env bash
set -euo pipefail

PORT="${1:-5567}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

export DATA_FORMULATOR_HOME="${PROJECT_ROOT}/.data_formulator"
export DF_PLUGIN_DIR="${PROJECT_ROOT}/tools/data-formulator/plugins"
export WORKSPACE_BACKEND="local"

mkdir -p "${DATA_FORMULATOR_HOME}" "${DF_PLUGIN_DIR}"

echo "Starting Data Formulator..."
echo "URL: http://localhost:${PORT}"
echo "DATA_FORMULATOR_HOME=${DATA_FORMULATOR_HOME}"
echo "DF_PLUGIN_DIR=${DF_PLUGIN_DIR}"

uvx data_formulator --port "${PORT}" --sandbox local
