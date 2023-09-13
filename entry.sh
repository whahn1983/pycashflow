#!/bin/sh

# start cron
exec /usr/sbin/crond -f -l 8

#flask migrate
exec /usr/local/bin/flask --app app db migrate

#run waitress
exec waitress-serve --listen=127.0.0.1:5000 --call app:create_app
