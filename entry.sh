#!/bin/sh

# Running as root here — fix ownership of any bind-mounted volumes so
# appuser can read/write them, regardless of host directory ownership.
chown -R appuser:appgroup /app/app/data
chown -R appuser:appgroup /app/migrations
chown appuser:appgroup /var/log/getemail.log

# Snapshot the full container environment so cron jobs can source it.
# busybox crond strips environment variables before running jobs, so we save
# the current env here (as root, before dropping privileges) and restore it
# inside each job via `. /app/crontab-env`.
export -p > /app/crontab-env

# Run crond as root so busybox can read /app/crontabs/appuser and drop to appuser per job
/usr/sbin/crond -f -l 8 -c /app/crontabs/ &

# Flask migrations as appuser
su-exec appuser /usr/local/bin/flask --app app db init
su-exec appuser /usr/local/bin/flask --app app db migrate
su-exec appuser /usr/local/bin/flask --app app db upgrade

# Run waitress as appuser (exec replaces the root shell — no root process remains)
exec su-exec appuser waitress-serve --listen=0.0.0.0:5000 --call app:create_app
