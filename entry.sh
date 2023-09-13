#!/bin/sh
/bin/touch debug0
# start cron
/usr/sbin/crond -f -l 8
/bin/touch debug1
#flask migrate
/usr/local/bin/flask --app app db migrate

/bin/touch debug2
#run waitress
/usr/local/bin/waitress-serve --listen=127.0.0.1:5000 --call app:create_app &

/bin/touch debug3
