#!/bin/sh

# start cron
/usr/sbin/crond -f -l 8 > /dev/null 2>&1 &

#flask migrate
/usr/local/bin/flask --app app db init
/usr/local/bin/flask --app app db migrate
/usr/local/bin/flask --app app db upgrade

#run waitress
exec waitress-serve --listen=0.0.0.0:5000 --call app:create_app
