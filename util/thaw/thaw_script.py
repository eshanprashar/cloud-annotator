# thaw_script.py
#
# Thaws upgraded (premium) user data
#
# Copyright (C) 2015-2024 Vas Vasiliadis
# University of Chicago
##
__author__ = "Vas Vasiliadis <vas@uchicago.edu>"

import boto3
import json
import os
import sys
import time

from botocore.exceptions import ClientError

# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

# Get configuration
from configparser import ConfigParser, ExtendedInterpolation

config = ConfigParser(os.environ, interpolation=ExtendedInterpolation())
config.read("../util_config.ini")
config.read("thaw_script_config.ini")

"""A16
Initiate thawing of archived objects from Glacier
"""


def handle_thaw_queue(glacier, sqs):


    # Read messages from the queue
    messages = sqs.receive_messages(MaxNumberOfMessages=int(config['sqs']['MaxMessages']), WaitTimeSeconds=int(config['sqs']['WaitTime']))    

    # Process messages received --> initiate restore from Glacier
    if len(messages) > 0:
        print(f'Received {str(len(messages))} messages. Now processing them...')

    for message in messages:
        sns_data = message.body
        sns_parameters = json.loads(json.loads(sns_data)['Message'])
        user_id = sns_parameters['user_id']
        archive_id = sns_parameters['archive_id']
        #bucket = sns_parameters['results_bucket']

        # Although this shouldn't change, check if user is still premium just to confirm
        user_profile = helpers.get_user_profile(id=user_id)
        user_role = user_profile.get('role')

        print(f"User is a {user_role}...initiating the restoring process")

        # Process messages --> initiate restore from Glacier
        print(f"The SNS topic name is {config['sns']['SnsRestoreArn']}")

        if user_role == "premium_user":
            try:
                # Source: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier/client/initiate_job.html
                glacier_parameters = {
                'Type': "archive-retrieval",
                'ArchiveId': archive_id,
                'SNSTopic': config['sns']["SnsRestoreArn"],
                'Description': user_id,
                'Tier': 'Expedited'
                }
                response = glacier.initiate_job(
                    vaultName=config['glacier']['VaultName'],
                    jobParameters=glacier_parameters
                    )
                print(f"Expedited retrieval initiated for archive {archive_id}")
                # Once the request fails, print the error
            except ClientError as e:
                print(f"Expedited request failed because of error: {e}")
                # Resubmit request using standard retrieval
                try:
                    glacier_parameters['Tier'] = 'Standard'
                    response = glacier.initiate_job(
                        vaultName=config['glacier']['VaultName'],
                        jobParameters=glacier_parameters
                        )
                    print(f"Standard retrieval initiated for archive {archive_id}")
                except ClientError as e:
                    print(f"Standard retrieval failed because of error: {e}")

        message.delete()
        print(f"Message deleted successfully!")

def main():
    # Add glacier connection details
    glacier = boto3.client('glacier', region_name=config['aws']['AwsRegionName'])

    # Get handles to resources
    sqs_client = boto3.resource('sqs',region_name=config['aws']['AwsRegionName'])
    print(config['sqs']['SqsThaw'])
    queue = sqs_client.get_queue_by_name(QueueName=config['sqs']['SqsThaw'])

    # Poll queue for new results and process them
    while True:
        print("Examining object thaw queue...Hang tight!")
        handle_thaw_queue(glacier, sqs=queue)


if __name__ == "__main__":
    main()

### EOF