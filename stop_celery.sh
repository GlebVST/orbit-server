#!/bin/bash
SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
BASEDIR="${SCRIPT_DIR}/celery"
celery multi stopwait w1 -A mysite --pidfile="${BASEDIR}/run/%n.pid" --logfile="${BASEDIR}/log/%n.log"
celery multi stopwait w2 -A mysite --pidfile="${BASEDIR}/run/%n.pid" --logfile="${BASEDIR}/log/%n.log"

# stop celery beat
pidfile="${BASEDIR}/run/beat.pid"
read pid <$pidfile
kill $pid
rm $pidfile
