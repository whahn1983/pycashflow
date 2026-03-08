#!/bin/sh

# Running as root here — fix ownership of any bind-mounted volumes so
# appuser can read/write them, regardless of host directory ownership.
chown -R appuser:appgroup /app/app/data
chown -R appuser:appgroup /app/migrations
chown appuser:appgroup /var/log/getemail.log

# Emit a startup marker to confirm log writeability and aid cron troubleshooting.
echo "[$(date +"%Y-%m-%dT%H:%M:%S%z")] entrypoint: container startup" >> /var/log/getemail.log 2>&1

# Snapshot the full container environment so cron jobs can source it.
# busybox crond strips environment variables before running jobs, so we save
# the current env here (as root, before dropping privileges) and restore it
# inside each job via `. /app/crontab-env`.
export -p > /app/crontab-env

# Run crond in daemon mode as root so it can read /app/crontabs/appuser
# and drop to appuser for each job. Logging to getemail.log keeps all email
# import diagnostics in one place.
/usr/sbin/crond -l 8 -L /var/log/getemail.log -c /app/crontabs/

# Flask migrations as appuser
su-exec appuser /usr/local/bin/flask --app app db init
su-exec appuser /usr/local/bin/flask --app app db migrate
su-exec appuser /usr/local/bin/flask --app app db upgrade

# Run waitress as appuser (exec replaces the root shell — no root process remains)
exec su-exec appuser waitress-serve --listen=0.0.0.0:5000 --call app:create_app
