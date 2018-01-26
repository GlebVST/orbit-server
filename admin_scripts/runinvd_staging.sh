#!/bin/bash
# This is meant to be called by a cron task on the orbit-staging server.
cd /home/ubuntu/orbit_server/orbit_server
/home/ubuntu/orbit_server/orbit_server/venv/bin/python manage.py inviterDiscount
/home/ubuntu/orbit_server/orbit_server/venv/bin/python manage.py completeDowngradeSubs
