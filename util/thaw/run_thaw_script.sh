#!/bin/bash

# run_thaw_script.sh
#
# Copyright (C) 2015-2024 Vas Vasiliadis
# University of Chicago
# Adapted for use in Genomic Annotator Service, built by Eshan Prashar, as a part of 
# graduate coursework at the University of Chicago

# Runs the Glacier thawing utility script
##

cd /home/ubuntu/gas/gas-eshanprashar/util/thaw
source /home/ubuntu/.virtualenvs/mpcs/bin/activate
/home/ubuntu/.virtualenvs/mpcs/bin/python /home/ubuntu/gas/gas-eshanprashar/util/thaw/thaw_script.py

### EOF