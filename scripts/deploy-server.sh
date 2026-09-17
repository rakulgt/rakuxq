#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "deploy-server.sh must run as root" >&2
  exit 1
fi

REVISION="${1:?revision is required}"
DOMAIN="${2:-xq.rakubank.com}"
PORT="${3:-8040}"
if [[ ! "${REVISION}" =~ ^[0-9a-f]{7,40}$ ]]; then
  echo "invalid revision" >&2
  exit 1
fi
if [[ "${DOMAIN}" != "xq.rakubank.com" || "${PORT}" != "8040" ]]; then
  echo "unexpected production target" >&2
  exit 1
fi

BASE=/opt/raku/portable/rakuxq
RELEASE_DIR="${BASE}/releases/${REVISION}"
MODELS_DIR="${BASE}/models"
SECRET_DIR=/opt/raku/secrets/rakuxq
LOG_DIR=/opt/raku/logs/rakuxq
AUDIT_DIR=${LOG_DIR}/interactions
BACKUP_DIR="/opt/raku/backups/rakuxq/$(date +%Y%m%d-%H%M%S)-${REVISION}"
ARCHIVE="/tmp/rakuxq-${REVISION}.tar.gz"
POSE_UPLOAD=/tmp/rakuxq-pose.onnx
LAYOUT_UPLOAD=/tmp/rakuxq-layout.onnx
KEY_DB_UPLOAD=/tmp/rakuxq-api-keys.sqlite3
NGINX_CONF=/etc/nginx/conf.d/xq-rakubank.conf
NGINX_ROUTES=/etc/nginx/snippets/rakuxq-api-routes.conf
SERVICE_CONF=/etc/systemd/system/rakuxq-api.service
AUDIT_RETENTION_SERVICE=/etc/systemd/system/rakuxq-audit-retention.service
AUDIT_RETENTION_TIMER=/etc/systemd/system/rakuxq-audit-retention.timer
LOGROTATE_CONF=/etc/logrotate.d/rakuxq
PREVIOUS_RELEASE=""

for required in "${ARCHIVE}" "${POSE_UPLOAD}" "${LAYOUT_UPLOAD}"; do
  if [[ ! -f "${required}" ]]; then
    echo "missing deployment input: ${required}" >&2
    exit 1
  fi
done

if [[ -L "${BASE}/current" ]]; then
  PREVIOUS_RELEASE="$(readlink -f "${BASE}/current")"
fi

mkdir -p \
  "${RELEASE_DIR}" \
  "${MODELS_DIR}" \
  "${SECRET_DIR}" \
  "${LOG_DIR}" \
  "${AUDIT_DIR}" \
  "${BACKUP_DIR}"
if ! getent passwd rakuxq >/dev/null; then
  useradd --system --home-dir /nonexistent --shell /sbin/nologin rakuxq
fi
if ! command -v setfacl >/dev/null; then
  echo "setfacl is required to grant the service account traverse-only secret access" >&2
  exit 1
fi
setfacl -m u:rakuxq:--x /opt/raku/secrets
chown rakuxq:rakuxq "${SECRET_DIR}" "${LOG_DIR}" "${AUDIT_DIR}"
chmod 700 "${SECRET_DIR}"
chmod 750 "${LOG_DIR}"
chmod 700 "${AUDIT_DIR}"

tar -xzf "${ARCHIVE}" -C "${RELEASE_DIR}"
install -o root -g rakuxq -m 0440 "${POSE_UPLOAD}" "${MODELS_DIR}/pose.onnx"
install -o root -g rakuxq -m 0440 "${LAYOUT_UPLOAD}" "${MODELS_DIR}/layout.onnx"
ln -sfn "${MODELS_DIR}/pose.onnx" "${RELEASE_DIR}/models/pose.onnx"
ln -sfn "${MODELS_DIR}/layout.onnx" "${RELEASE_DIR}/models/layout.onnx"
python3 "${RELEASE_DIR}/scripts/verify_models.py"

python3 -m venv "${RELEASE_DIR}/.venv"
"${RELEASE_DIR}/.venv/bin/python" -m pip install --upgrade pip
"${RELEASE_DIR}/.venv/bin/python" -m pip install "${RELEASE_DIR}/apps/api"

if [[ -f "${KEY_DB_UPLOAD}" && ! -f "${SECRET_DIR}/api-keys.sqlite3" ]]; then
  install -o rakuxq -g rakuxq -m 0600 "${KEY_DB_UPLOAD}" "${SECRET_DIR}/api-keys.sqlite3"
fi
if [[ ! -f "${SECRET_DIR}/api-keys.sqlite3" ]]; then
  runuser -u rakuxq -- "${RELEASE_DIR}/.venv/bin/python" -m rakuxq_api.key_cli \
    --database "${SECRET_DIR}/api-keys.sqlite3" list >/dev/null
fi

cat >"${SECRET_DIR}/api.env" <<EOF
RAKUXQ_POSE_MODEL=${MODELS_DIR}/pose.onnx
RAKUXQ_LAYOUT_MODEL=${MODELS_DIR}/layout.onnx
RAKUXQ_MODEL_VERSION=cchess-baseline-2025-03-19
RAKUXQ_ORT_INTRA_OP_THREADS=2
RAKUXQ_REQUIRE_API_KEY=1
RAKUXQ_API_KEYS_DB=${SECRET_DIR}/api-keys.sqlite3
RAKUXQ_RENEWAL_WECHAT=lgtqcn
RAKUXQ_RENEWAL_PRICE_CNY=39
RAKUXQ_RENEWAL_PERIOD_DAYS=365
RAKUXQ_AUDIT_DIR=${AUDIT_DIR}
RAKUXQ_AUDIT_RETENTION_HOURS=12
RAKUXQ_AUDIT_MAX_TOTAL_BYTES=2147483648
EOF
chown root:rakuxq "${SECRET_DIR}/api.env"
chmod 0640 "${SECRET_DIR}/api.env"

mkdir -p "$(dirname "${NGINX_ROUTES}")"
if [[ -f "${NGINX_CONF}" ]]; then
  cp -a "${NGINX_CONF}" "${BACKUP_DIR}/xq-rakubank.conf"
fi
if [[ -f "${NGINX_ROUTES}" ]]; then
  cp -a "${NGINX_ROUTES}" "${BACKUP_DIR}/rakuxq-api-routes.conf"
fi
if [[ -f "${SERVICE_CONF}" ]]; then
  cp -a "${SERVICE_CONF}" "${BACKUP_DIR}/rakuxq-api.service"
fi
for managed in "${AUDIT_RETENTION_SERVICE}" "${AUDIT_RETENTION_TIMER}" "${LOGROTATE_CONF}"; do
  if [[ -f "${managed}" ]]; then
    cp -a "${managed}" "${BACKUP_DIR}/$(basename "${managed}")"
  fi
done
install -o root -g root -m 0644 "${RELEASE_DIR}/infra/rakuxq-api.service" "${SERVICE_CONF}"
install -o root -g root -m 0644 \
  "${RELEASE_DIR}/infra/rakuxq-audit-retention.service" "${AUDIT_RETENTION_SERVICE}"
install -o root -g root -m 0644 \
  "${RELEASE_DIR}/infra/rakuxq-audit-retention.timer" "${AUDIT_RETENTION_TIMER}"
install -o root -g root -m 0644 \
  "${RELEASE_DIR}/infra/rakuxq-logrotate.conf" "${LOGROTATE_CONF}"
install -o root -g root -m 0644 "${RELEASE_DIR}/infra/xq-rakubank-routes.conf" "${NGINX_ROUTES}"
if [[ -f /etc/letsencrypt/live/xq.rakubank.com/fullchain.pem && -f /etc/letsencrypt/live/xq.rakubank.com/privkey.pem ]]; then
  install -o root -g root -m 0644 "${RELEASE_DIR}/infra/xq-rakubank-nginx-tls.conf" "${NGINX_CONF}"
else
  install -o root -g root -m 0644 "${RELEASE_DIR}/infra/xq-rakubank-nginx.conf" "${NGINX_CONF}"
fi

systemd-analyze verify \
  "${SERVICE_CONF}" \
  "${AUDIT_RETENTION_SERVICE}" \
  "${AUDIT_RETENTION_TIMER}"
/usr/sbin/logrotate --debug "${LOGROTATE_CONF}" >/dev/null

ln -sfn "${RELEASE_DIR}" "${BASE}/current"
systemctl daemon-reload
systemctl enable rakuxq-api.service >/dev/null
systemctl enable --now rakuxq-audit-retention.timer >/dev/null
if ! nginx -t; then
  if [[ -f "${BACKUP_DIR}/xq-rakubank.conf" ]]; then
    cp -a "${BACKUP_DIR}/xq-rakubank.conf" "${NGINX_CONF}"
  else
    rm -f "${NGINX_CONF}"
  fi
  if [[ -f "${BACKUP_DIR}/rakuxq-api-routes.conf" ]]; then
    cp -a "${BACKUP_DIR}/rakuxq-api-routes.conf" "${NGINX_ROUTES}"
  else
    rm -f "${NGINX_ROUTES}"
  fi
  nginx -t
  exit 1
fi
systemctl reload nginx
systemctl restart rakuxq-api.service
systemctl start rakuxq-audit-retention.service

healthy=0
for _ in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${PORT}/healthz" | grep -q '"status":"ok"'; then
    healthy=1
    break
  fi
  sleep 2
done
if [[ "${healthy}" -ne 1 ]]; then
  if [[ -n "${PREVIOUS_RELEASE}" ]]; then
    ln -sfn "${PREVIOUS_RELEASE}" "${BASE}/current"
    systemctl restart rakuxq-api.service || true
  fi
  systemctl status rakuxq-api.service --no-pager >&2 || true
  journalctl -u rakuxq-api.service -n 60 --no-pager >&2 || true
  exit 1
fi

rm -f "${ARCHIVE}" "${POSE_UPLOAD}" "${LAYOUT_UPLOAD}" "${KEY_DB_UPLOAD}"
echo "deployed ${REVISION} to ${DOMAIN} on 127.0.0.1:${PORT}"
echo "backup: ${BACKUP_DIR}"
