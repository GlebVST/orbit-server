#!/bin/bash
# http://celery.readthedocs.org/en/latest/reference/celery.bin.multi.html#module-celery.bin.multi
# From celery docs: Pidfiles and logfiles are stored in the current directory by default.
#   Use --pidfile and --logfile argument to change this.
#   The abbreviation %n will be expanded to the current node name.
#   To stop the worker, need to pass in the same pidfile,logfile as what was used to start it
#
# Create 2 workers:
#   concurrency=1 because t2.small has only 1 core.
SCRIPT_DIR=$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")
BASEDIR="${SCRIPT_DIR}/celery"
celery multi start w1 w2 -A mysite -c1 -l info --pidfile="${BASEDIR}/run/%n.pid" --logfile="${BASEDIR}/log/%n.log"

# Start celery beat
celery -A mysite beat -l info -s "${BASEDIR}/run/celerybeat-schedule" --pidfile="${BASEDIR}/run/beat.pid" --logfile="${BASEDIR}/log/beat.log" --detach
