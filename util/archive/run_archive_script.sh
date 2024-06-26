#!/bin/bash

# run_archive_script.sh
#
# Copyright (C) 2015-2024 Vas Vasiliadis
# University of Chicago
# Adapted for use in Genomic Annotator Service, built by Eshan Prashar, as a part of 
# graduate coursework at the University of Chicago

# Runs the archive utility script
##

cd /home/ubuntu/gas/gas-eshanprashar/util/archive
source /home/ubuntu/.virtualenvs/mpcs/bin/activate
/home/ubuntu/.virtualenvs/mpcs/bin/python /home/ubuntu/gas/gas-eshanprashar/util/archive/archive_script.py

### EOF