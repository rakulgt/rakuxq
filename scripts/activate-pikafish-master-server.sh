#!/usr/bin/env bash

set -euo pipefail

# Atomically switch the private non-commercial RakuXQ engine installation to
# the already staged, pinned Pikafish master pair. The previous api.env and
# engine directory remain available for immediate rollback.

ENGINE_COMMIT="1c66b9b21cf2f280ce3b3ffa80c1c6609f2b29ff"
ENGINE_SHA256="0d7ff804a8c07022cb1bac10c5e82c6e6e40e4ce98e26aa1258fda339904dfb9"
NETWORK_SHA256="6b74ac7bbd299dc26a17803135b616eda9248bef0cbfc7b811bfcf981832ba29"
ENGINE_DIR="/opt/raku/portable/rakuxq/engines/pikafish-master-${ENGINE_COMMIT:0:12}"
ENGINE_PATH="${ENGINE_DIR}/pikafish"
NETWORK_PATH="${ENGINE_DIR}/pikafish.nnue"
ENGINE_VERSION="Pikafish master 2026-10-01 (${ENGINE_COMMIT:0:8})"
ENV_FILE="/opt/raku/secrets/rakuxq/api.env"
BACKUP_DIR="/opt/raku/backups/rakuxq/$(date +%Y%m%d-%H%M%S)-pikafish-${ENGINE_COMMIT:0:8}"
TEMP_ENV=""
ACTIVATED=false

cleanup() {
  [[ -z "${TEMP_ENV}" || ! -e "${TEMP_ENV}" ]] || rm -f -- "${TEMP_ENV}"
}
trap cleanup EXIT

rollback() {
  if [[ "${ACTIVATED}" == true && -r "${BACKUP_DIR}/api.env" ]]; then
    cp -p "${BACKUP_DIR}/api.env" "${ENV_FILE}"
    systemctl restart rakuxq-api.service || true
  fi
}
trap rollback ERR

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This activation script must run as root." >&2
  exit 1
fi

[[ -x "${ENGINE_PATH}" ]] || { echo "Missing engine: ${ENGINE_PATH}" >&2; exit 1; }
[[ -r "${NETWORK_PATH}" ]] || { echo "Missing network: ${NETWORK_PATH}" >&2; exit 1; }
[[ -r "${ENV_FILE}" ]] || { echo "Missing environment file: ${ENV_FILE}" >&2; exit 1; }

echo "${ENGINE_SHA256}  ${ENGINE_PATH}" | sha256sum --check --status
echo "${NETWORK_SHA256}  ${NETWORK_PATH}" | sha256sum --check --status

UCI_OUTPUT="$({
  printf 'uci\n'
  printf 'setoption name EvalFile value %s\n' "${NETWORK_PATH}"
  printf 'isready\nquit\n'
} | "${ENGINE_PATH}")"
grep -q '^uciok$' <<<"${UCI_OUTPUT}"
grep -q '^readyok$' <<<"${UCI_OUTPUT}"
grep -q "${ENGINE_COMMIT:0:8}" <<<"${UCI_OUTPUT}"

install -d -m 0700 "${BACKUP_DIR}"
cp -p "${ENV_FILE}" "${BACKUP_DIR}/api.env"

TEMP_ENV="$(mktemp "${ENV_FILE}.XXXXXX")"
awk \
  -v engine_path="${ENGINE_PATH}" \
  -v network_path="${NETWORK_PATH}" \
  -v engine_version="${ENGINE_VERSION}" '
    BEGIN { seen_path=0; seen_network=0; seen_version=0 }
    /^RAKUXQ_ENGINE_PATH=/ {
      print "RAKUXQ_ENGINE_PATH=" engine_path; seen_path=1; next
    }
    /^RAKUXQ_ENGINE_NETWORK=/ {
      print "RAKUXQ_ENGINE_NETWORK=" network_path; seen_network=1; next
    }
    /^RAKUXQ_ENGINE_VERSION=/ {
      print "RAKUXQ_ENGINE_VERSION=" engine_version; seen_version=1; next
    }
    { print }
    END {
      if (!seen_path) print "RAKUXQ_ENGINE_PATH=" engine_path
      if (!seen_network) print "RAKUXQ_ENGINE_NETWORK=" network_path
      if (!seen_version) print "RAKUXQ_ENGINE_VERSION=" engine_version
    }
  ' "${ENV_FILE}" >"${TEMP_ENV}"
chown --reference="${ENV_FILE}" "${TEMP_ENV}"
chmod --reference="${ENV_FILE}" "${TEMP_ENV}"
mv -f "${TEMP_ENV}" "${ENV_FILE}"
TEMP_ENV=""
ACTIVATED=true

systemctl restart rakuxq-api.service
systemctl is-active --quiet rakuxq-api.service
HEALTH=""
for _ in $(seq 1 30); do
  if HEALTH="$(curl --fail --silent --show-error --connect-timeout 1 --max-time 2 http://127.0.0.1:8040/healthz 2>/dev/null)"; then
    break
  fi
  sleep 1
done
[[ -n "${HEALTH}" ]] || { echo "RakuXQ health endpoint did not become ready within 30 seconds." >&2; exit 1; }
grep -q "${ENGINE_COMMIT:0:8}" <<<"${HEALTH}"

trap - ERR
echo "Activated ${ENGINE_VERSION}"
echo "Backup: ${BACKUP_DIR}/api.env"
echo "Health: ${HEALTH}"
