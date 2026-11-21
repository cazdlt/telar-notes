#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_dir="$(cd -- "${script_dir}/.." && pwd)"
env_file="${project_dir}/.env"

if [[ ! -f "${env_file}" ]]; then
  printf 'Missing %s. Copy .env.example to .env and configure VAULT_PATH first.\n' "${env_file}" >&2
  exit 2
fi

set -a
# shellcheck source=/dev/null
source "${env_file}"
set +a

export TELAR_UID="${TELAR_UID:-$(id -u)}"
export TELAR_GID="${TELAR_GID:-$(id -g)}"
export TELAR_PORT="${TELAR_PORT:-7731}"
export TELAR_CONFIG_PATH="${TELAR_CONFIG_PATH:-${project_dir}/.telar-config}"

if [[ -z "${VAULT_PATH:-}" || ! -d "${VAULT_PATH}" ]]; then
  printf 'VAULT_PATH does not exist or is not a directory: %s\n' "${VAULT_PATH:-<unset>}" >&2
  exit 2
fi

# Create config dir as the host user so Docker does not create it owned by root.
mkdir -p "${TELAR_CONFIG_PATH}"

cd "${project_dir}"
docker compose up -d --build

health_url="http://127.0.0.1:${TELAR_PORT}/api/vaults"
for _ in $(seq 1 20); do
  if curl -fsS -H "Host: 127.0.0.1:${TELAR_PORT}" "${health_url}" >/dev/null 2>&1; then
    printf 'Telar Notes is up at http://127.0.0.1:%s\n' "${TELAR_PORT}"
    exit 0
  fi
  sleep 1
done

printf 'Container started, but %s did not respond in time. Check `docker compose logs`.\n' "${health_url}" >&2
exit 1
