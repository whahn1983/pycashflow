#!/bin/sh

# Configure container local timezone from TZ env var, or /app/app/.env (defaults to UTC).
#
# Runtime env var takes precedence. If it is missing, attempt to read TZ from
# the mounted .env file so timezone configuration works even when users only
# set TZ there.
TZ_VALUE="${TZ:-}"
if [ -z "${TZ_VALUE}" ] && [ -f "/app/app/.env" ]; then
    TZ_VALUE="$(awk -F= '
        /^[[:space:]]*TZ[[:space:]]*=/ {
            sub(/^[[:space:]]*TZ[[:space:]]*=[[:space:]]*/, "", $0)
            gsub(/^[[:space:]]+|[[:space:]]+$/, "", $0)
            gsub(/^["'"'"']|["'"'"']$/, "", $0)
            print $0
            exit
        }
    ' /app/app/.env)"
fi
TZ_VALUE="${TZ_VALUE:-UTC}"
if [ -f "/usr/share/zoneinfo/${TZ_VALUE}" ]; then
    ln -snf "/usr/share/zoneinfo/${TZ_VALUE}" /etc/localtime
    echo "${TZ_VALUE}" > /etc/timezone
else
    echo "Invalid TZ '${TZ_VALUE}', falling back to UTC."
    TZ_VALUE="UTC"
    ln -snf /usr/share/zoneinfo/UTC /etc/localtime
    echo "UTC" > /etc/timezone
fi
export TZ="${TZ_VALUE}"

# Running as root here — fix ownership of any bind-mounted volumes so
# appuser can read/write them, regardless of host directory ownership.
chown -R appuser:appgroup /app/app/data
chown -R appuser:appgroup /app/migrations
chown appuser:appgroup /app/getemail.log
# crond.log is written by root crond — leave as root:root

# Run crond in foreground mode (-f) so it doesn't double-fork into an
# unreachable daemon; & sends it to the background so this script continues.
# Daemon log goes to /app/crond.log (separate from job output in getemail.log).
/usr/sbin/crond -f -l 8 -L /app/crond.log -c /app/crontabs/ &

# Apply checked-in migrations as appuser (never generate migrations at startup)
su-exec appuser /usr/local/bin/flask --app app db upgrade

# Derive safe Gunicorn defaults (override with env vars as needed).
CPU_COUNT="$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 1)"
case "${CPU_COUNT}" in
    ''|*[!0-9]*|0) CPU_COUNT=1 ;;
esac
DEFAULT_GUNICORN_WORKERS=$((CPU_COUNT * 2 + 1))

# Flask-Limiter defaults to in-memory storage (memory://), which is process-local.
# Keep a single worker by default unless a shared rate-limit backend is configured.
if [ -n "${GUNICORN_WORKERS:-}" ]; then
    RESOLVED_GUNICORN_WORKERS="${GUNICORN_WORKERS}"
elif [ -z "${RATELIMIT_STORAGE_URI:-}" ] || [ "${RATELIMIT_STORAGE_URI}" = "memory://" ]; then
    RESOLVED_GUNICORN_WORKERS=1
else
    RESOLVED_GUNICORN_WORKERS="${DEFAULT_GUNICORN_WORKERS}"
fi

GUNICORN_WORKERS="${RESOLVED_GUNICORN_WORKERS}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-120}"

echo "Starting Gunicorn: workers=${GUNICORN_WORKERS}, timeout=${GUNICORN_TIMEOUT}, bind=0.0.0.0:5000"

# Run gunicorn as appuser (exec replaces the root shell — no root process remains)
exec su-exec appuser gunicorn \
    --bind 0.0.0.0:5000 \
    --workers "${GUNICORN_WORKERS}" \
    --worker-class sync \
    --timeout "${GUNICORN_TIMEOUT}" \
    --access-logfile - \
    --error-logfile - \
    --capture-output \
    'app:create_app()'
