#!/usr/bin/env bash

set -euo pipefail

# Install one exact Pikafish master commit and its matching rolling network.
# This script stages verified assets only; it never edits api.env or restarts RakuXQ.

ENGINE_COMMIT="1c66b9b21cf2f280ce3b3ffa80c1c6609f2b29ff"
NETWORK_URL="https://github.com/official-pikafish/Networks/releases/download/master-net/pikafish.nnue"
NETWORK_SHA256="6b74ac7bbd299dc26a17803135b616eda9248bef0cbfc7b811bfcf981832ba29"
PRELOADED_NETWORK="${RAKUXQ_PRELOADED_NETWORK:-/tmp/rakuxq-pikafish-master.nnue}"
PREBUILT_ENGINE="${RAKUXQ_PREBUILT_ENGINE:-}"
ENGINE_ROOT="/opt/raku/portable/rakuxq/engines"
TARGET_DIR="${ENGINE_ROOT}/pikafish-master-${ENGINE_COMMIT:0:12}"
STAGE_DIR="${TARGET_DIR}.stage.$$"
BUILD_DIR="$(mktemp -d /tmp/rakuxq-pikafish.XXXXXX)"

cleanup() {
  rm -rf -- "${BUILD_DIR}"
  [[ ! -e "${STAGE_DIR}" ]] || rm -rf -- "${STAGE_DIR}"
}
trap cleanup EXIT

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This installer must run as root." >&2
  exit 1
fi

for command_name in curl sha256sum install; do
  command -v "${command_name}" >/dev/null || {
    echo "Missing required command: ${command_name}" >&2
    exit 1
  }
done

mkdir -p "${ENGINE_ROOT}"
if [[ -e "${TARGET_DIR}" ]]; then
  echo "Refusing to overwrite existing target: ${TARGET_DIR}" >&2
  exit 1
fi

if [[ -r "${PRELOADED_NETWORK}" ]]; then
  install -m 0600 "${PRELOADED_NETWORK}" "${BUILD_DIR}/pikafish.nnue"
else
  curl --fail --location --retry 3 --output "${BUILD_DIR}/pikafish.nnue" "${NETWORK_URL}"
fi
echo "${NETWORK_SHA256}  ${BUILD_DIR}/pikafish.nnue" | sha256sum --check --status

if [[ -n "${PREBUILT_ENGINE}" ]]; then
  [[ -x "${PREBUILT_ENGINE}" ]] || {
    echo "Prebuilt engine is not executable: ${PREBUILT_ENGINE}" >&2
    exit 1
  }
  ENGINE_BINARY="${PREBUILT_ENGINE}"
  BUILD_ARCH="x86-64-vnni512 (GitHub Actions)"
else
  for command_name in git make g++; do
    command -v "${command_name}" >/dev/null || {
      echo "Missing required command: ${command_name}" >&2
      exit 1
    }
  done
  git -C "${BUILD_DIR}" init --quiet source
  git -C "${BUILD_DIR}/source" remote add origin https://github.com/official-pikafish/Pikafish.git
  git -C "${BUILD_DIR}/source" fetch --quiet --depth 1 origin "${ENGINE_COMMIT}"
  git -C "${BUILD_DIR}/source" checkout --quiet --detach FETCH_HEAD

  ACTUAL_COMMIT="$(git -C "${BUILD_DIR}/source" rev-parse HEAD)"
  if [[ "${ACTUAL_COMMIT}" != "${ENGINE_COMMIT}" ]]; then
    echo "Engine commit mismatch: expected ${ENGINE_COMMIT}, got ${ACTUAL_COMMIT}" >&2
    exit 1
  fi

  # The upstream build target checks for the default network before compiling.
  install -m 0444 "${BUILD_DIR}/pikafish.nnue" "${BUILD_DIR}/source/src/pikafish.nnue"
  # Production hosts should normally use a prebuilt artifact. This fallback is
  # intentionally single-job and low-priority for small maintenance servers.
  nice -n 19 ionice -c3 make -C "${BUILD_DIR}/source/src" -j1 build ARCH=native
  ENGINE_BINARY="${BUILD_DIR}/source/src/pikafish"
  BUILD_ARCH="native"
fi

if [[ ! -x "${ENGINE_BINARY}" ]]; then
  echo "Compiled engine was not found at ${ENGINE_BINARY}" >&2
  exit 1
fi

install -d -m 0755 "${STAGE_DIR}"
install -m 0555 "${ENGINE_BINARY}" "${STAGE_DIR}/pikafish"
install -m 0444 "${BUILD_DIR}/pikafish.nnue" "${STAGE_DIR}/pikafish.nnue"

ENGINE_SHA256="$(sha256sum "${STAGE_DIR}/pikafish" | awk '{print $1}')"
{
  printf 'upstream_repository=%s\n' 'https://github.com/official-pikafish/Pikafish'
  printf 'engine_commit=%s\n' "${ENGINE_COMMIT}"
  printf 'engine_sha256=%s\n' "${ENGINE_SHA256}"
  printf 'network_url=%s\n' "${NETWORK_URL}"
  printf 'network_sha256=%s\n' "${NETWORK_SHA256}"
  printf 'build_arch=%s\n' "${BUILD_ARCH}"
  printf 'built_at=%s\n' "$(date --iso-8601=seconds)"
} >"${STAGE_DIR}/SOURCE.txt"
chmod 0444 "${STAGE_DIR}/SOURCE.txt"

UCI_OUTPUT="$({
  printf 'uci\n'
  printf 'setoption name EvalFile value %s\n' "${STAGE_DIR}/pikafish.nnue"
  printf 'isready\nquit\n'
} | "${STAGE_DIR}/pikafish")"

grep -q '^uciok$' <<<"${UCI_OUTPUT}"
grep -q '^readyok$' <<<"${UCI_OUTPUT}"
grep -q "${ENGINE_COMMIT:0:8}" <<<"${UCI_OUTPUT}"

mv "${STAGE_DIR}" "${TARGET_DIR}"

echo "Staged verified Pikafish candidate:"
echo "  directory: ${TARGET_DIR}"
echo "  commit: ${ENGINE_COMMIT}"
echo "  engine SHA-256: ${ENGINE_SHA256}"
echo "  network SHA-256: ${NETWORK_SHA256}"
