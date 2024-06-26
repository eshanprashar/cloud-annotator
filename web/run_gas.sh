#!/bin/bash

# run_gas.sh
#
# Copyright (C) 2015-2023 Vas Vasiliadis
# University of Chicago
#
# Runs the GAS app using a production-grade WSGI server (uwsgi)
#
# Adapted for use in Genomic Annotator Service, built by Eshan Prashar, as a part of 
# graduate coursework at the University of Chicago
##

SSL_CERT_PATH=/usr/local/src/ssl/ucmpcs.org.crt
SSL_KEY_PATH=/usr/local/src/ssl/ucmpcs.org.key

cd /home/ubuntu/gas/gas-eshanprashar/ #modified this line

if [ -f "/home/ubuntu/gas/.env" ]; then
    source /home/ubuntu/gas/.env
else
    export GAS_WEB_APP_HOME=/home/ubuntu/gas/gas-eshanprashar/web #modified this line
    export GAS_LOG_FILE_NAME=gas.log
    export GAS_SOURCE_HOST=0.0.0.0
    export GAS_HOST_PORT=4433
    export ACCOUNTS_DATABASE_TABLE=`cat /home/ubuntu/.launch_user`"_accounts"
fi

# Kill any other process running/listening on our port
#sudo kill -9 `sudo lsof -t -i:$GAS_HOST_PORT`

# Create the log directory and file, if it doesn't exist
[[ -d $GAS_WEB_APP_HOME/log ]] || mkdir $GAS_WEB_APP_HOME/log
if [ ! -e $GAS_WEB_APP_HOME/log/$GAS_LOG_FILE_NAME ]; then
    touch $GAS_WEB_APP_HOME/log/$GAS_LOG_FILE_NAME;
fi

LOG_TARGET=$GAS_WEB_APP_HOME/log/$GAS_LOG_FILE_NAME

if [ "$1" = "console" ]; then
    # Start the web server and redirect console output to the terminal
    /home/ubuntu/.virtualenvs/mpcs/bin/uwsgi \
        --chdir $GAS_WEB_APP_HOME \
        --enable-threads \
        --https $GAS_SOURCE_HOST:$GAS_HOST_PORT,$SSL_CERT_PATH,$SSL_KEY_PATH \
        --log-master \
        --manage-script-name \
        --mount /gas=app:app \
        --socket /tmp/gas.sock \
        --vacuum
else
    # Start the web server and redirect console output to the log file
    /home/ubuntu/.virtualenvs/mpcs/bin/uwsgi \
        --chdir $GAS_WEB_APP_HOME \
        --enable-threads \
        --https $GAS_SOURCE_HOST:$GAS_HOST_PORT,$SSL_CERT_PATH,$SSL_KEY_PATH \
        --log-master \
        --logger file:logfile=$LOG_TARGET,maxsize=500000 \
        --manage-script-name \
        --master \
        --mount /gas=app:app \
        --socket /tmp/gas.sock \
        --processes 1 \
        --vacuum
fi

### EOF
