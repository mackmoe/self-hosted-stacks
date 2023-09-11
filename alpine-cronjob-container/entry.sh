#!/bin/sh

# start cron
/usr/sbin/crond -f -l 8 && \
/bin/sh script.sh