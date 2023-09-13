#!/bin/sh

# start cron
/usr/sbin/crond -f -l 8 &

#flask migrate
/usr/local/bin/flask --app app db migrate

#run waitress
/usr/local/bin/waitress-serve --listen=127.0.0.1:5000 --call app:create_app &
