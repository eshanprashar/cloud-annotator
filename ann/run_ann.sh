#!/bin/bash

# run_ann.sh
#
# Copyright (C) 2011-2019 Vas Vasiliadis
# University of Chicago
# Adapted for use in Genomic Annotator Service, built by Eshan Prashar, as a part of 
# graduate coursework at the University of Chicago

# Runs the annotator script

cd /home/ubuntu/gas/gas-eshanprashar/ann
source /home/ubuntu/.virtualenvs/mpcs/bin/activate
/home/ubuntu/.virtualenvs/mpcs/bin/python /home/ubuntu/gas/gas-eshanprashar/ann/annotator.py

### EOF