#!/bin/sh

# start cron
/usr/sbin/crond -f -l 8 > /dev/null 2>&1 & disown

#flask migrate
/usr/local/bin/flask --app app db migrate > /dev/null 2>&1

#run waitress
exec waitress-serve --listen=0.0.0.0:5000 --call app:create_app
