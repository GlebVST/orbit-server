#!/bin/bash
# This is meant to be called by a cron task on the prod admin server.
# When called on 4/1: generate report for Q1 (1/1 - 3/30)
# When called on 7/1: generate report for Q2 (4/1 - 6/30)
# When called on 4/1: generate report for Q3 (7/1 - 9/30)
# When called on 1/1: generate report for Q4 (10/1 - 12/31) of prior year
cd /home/ubuntu/orbit_server
/home/ubuntu/virtualenvs/venv/bin/python manage.py makeTuftsReport
