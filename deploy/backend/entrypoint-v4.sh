#!/bin/sh
set -eu

read_secret_into_env() {
  variable="$1"
  file_variable="${variable}_FILE"
  eval "file_path=\${$file_variable:-}"
  if [ -n "$file_path" ]; then
    if [ ! -r "$file_path" ]; then
      echo "required secret file for $variable is unreadable" >&2
      exit 78
    fi
    value="$(cat "$file_path")"
    case "$value" in
      *"
"*|*"
"*)
        echo "secret file for $variable contains a newline" >&2
        exit 78
        ;;
    esac
    export "$variable=$value"
  fi
}

read_secret_into_env DATABASE_URL
read_secret_into_env INGRESS_DATABASE_URL
read_secret_into_env WORKER_DATABASE_URL
read_secret_into_env GATEWAY_SHARED_SECRET
read_secret_into_env COMPLIANCE_IDENTIFIER_PEPPER

mode="${1:-api}"
shift || true

case "$mode" in
  migrate)
    alembic upgrade head
    alembic -c alembic-compliance.ini upgrade head
    ;;
  api)
    exec uvicorn app.production_v4:app \
      --host 0.0.0.0 \
      --port "${PORT:-8000}" \
      --proxy-headers \
      --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:?required}"
    ;;
  worker)
    exec python -m workers.integration_worker "$@"
    ;;
  *)
    echo "unknown entrypoint mode: $mode" >&2
    exit 64
    ;;
esac
