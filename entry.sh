#!/bin/sh

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

# Flask migrations as appuser
su-exec appuser /usr/local/bin/flask --app app db init
su-exec appuser /usr/local/bin/flask --app app db migrate
su-exec appuser /usr/local/bin/flask --app app db upgrade

# Run waitress as appuser (exec replaces the root shell — no root process remains)
exec su-exec appuser waitress-serve --listen=0.0.0.0:5000 --call app:create_app
