#!/bin/bash
# This is meant to be called by a cron task on the admin server.
# 2019-03-18: only recompute existing goals since this is run hourly.
cd /home/ubuntu/orbit_server
##/home/ubuntu/virtualenvs/venv/bin/python manage.py rematchGoals
/home/ubuntu/virtualenvs/venv/bin/python manage.py recomputeUserGoals
