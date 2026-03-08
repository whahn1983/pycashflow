#!/bin/sh

# Running as root here — fix ownership of any bind-mounted volumes so
# appuser can read/write them, regardless of host directory ownership.
chown -R appuser:appgroup /app/app/data
chown appuser:appgroup /var/log/getemail.log

# Drop to appuser for cron (busybox crond reads /app/crontabs/appuser)
su-exec appuser /usr/sbin/crond -f -l 8 -c /app/crontabs/ > /dev/null 2>&1 &

# Flask migrations as appuser
su-exec appuser /usr/local/bin/flask --app app db init
su-exec appuser /usr/local/bin/flask --app app db migrate
su-exec appuser /usr/local/bin/flask --app app db upgrade

# Run waitress as appuser (exec replaces the root shell — no root process remains)
exec su-exec appuser waitress-serve --listen=0.0.0.0:5000 --call app:create_app
