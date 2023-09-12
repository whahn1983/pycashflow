#!/bin/sh

# start cron
/usr/sbin/crond -f -l 8

#flask migrate
flask --app app db migrate

#run waitress
waitress --listen=127.0.0.1:5000 --call app:create_app