# archive_script.py
#
# Archive free user data
#
# Copyright (C) 2015-2023 Vas Vasiliadis
# University of Chicago
# Adapted for use in Genomic Annotator Service, built by Eshan Prashar, as a part of 
# graduate coursework at the University of Chicago

__author__ = "Eshan Prashar <eshanprashar@uchicago.edu>"

import boto3
import time
import os
import sys
import json
from botocore.exceptions import ClientError
from botocore.client import Config

# Import utility helpers
sys.path.insert(1, os.path.realpath(os.path.pardir))
import helpers

# Get configuration
from configparser import ConfigParser, ExtendedInterpolation

config = ConfigParser(os.environ, interpolation=ExtendedInterpolation())
config.read("../util_config.ini")
config.read("archive_script_config.ini")

"""A14
Archive free user results files
"""


def handle_archive_queue(s3, dynamo_table, glacier, sqs):

    # Read messages from the queue
    messages = sqs.receive_messages(MaxNumberOfMessages=int(config['sqs']['MaxMessages']), WaitTimeSeconds=int(config['sqs']['WaitTime']))    

    # Process messages received
    if len(messages) > 0:
        print(f'Received {str(len(messages))} messages. Now processing them...')

    for message in messages:
        sns_data = message.body
        sns_parameters = json.loads(json.loads(sns_data)['Message'])
        user_id = sns_parameters['user_id']
        job_id = sns_parameters['job_id']
        #filename = sns_parameters['input_file_name']
        bucket = sns_parameters['s3_results_bucket']
        results_file = sns_parameters['s3_key_result_file']

        # Check if user_id is still free 
        user_profile = helpers.get_user_profile(id=user_id)
        user_role = user_profile.get('role')

        print(f"User is a {user_role}...Processing that information")

        # Process messages --> archive results file if user is still free
        if user_role == "free_user":
            try:
                # Get the results file content from DynamoDB
                response = dynamo_table.get_item(Key={'job_id': job_id})
                item = response.get('Item')
                results_file = item['s3_key_result_file']
                print(f"File obtained for archiving--{results_file}")

                # Upload the results file to Glacier
                archive_response = glacier.upload_archive(vaultName=config['glacier']['VaultName'], body=results_file)
                print(f"Archive request completed. Results file for job_id {job_id} archived successfully.")
            except ClientError as e:
                print(f"Error archiving results file for job_id {job_id}: {e}")

            print("Now adding archive ID to dynamo...")
            try:
                # Add archive ID to row in DynamoDB
                archive_id = archive_response['archiveId']
                dynamo_table.update_item(
                    Key={'job_id': job_id},
                    UpdateExpression='SET results_file_archive_id = :archive_id',
                    ExpressionAttributeValues={':archive_id': archive_id}
                )
                print("Archive ID added to dynamo...")
            except ClientError as e:
                print(f"Error updating {dynamo_table} with archive ID {archive_id}: {e}")

            print("Now deleting results file from dynamo")
            try:
                # Delete results file from DynamoDB
                dynamo_table.update_item(
                    Key={'job_id': job_id},\
                    UpdateExpression='REMOVE s3_key_result_file'
                    )

                print("S3 file deleted from dynamo")
            except ClientError as e:
                print(f"Error removing results file from {dynamo_table}: {e}")

            print("Now deleting results file from S3 bucket...")
            try:

                # Delete file from S3 bucket
                # Construct the s3 key
                object_key = (config["s3"]["KeyPrefix"]
                + user_id
                + "/"
                + job_id
                + "~"
                + results_file
            )
                s3.delete_object(Bucket=bucket, Key=object_key)
                print(f"Results file deleted from {bucket}...")
            except ClientError as e:
                print(f"Error removing results file from {bucket}: {e}")

        # Delete messages
        message.delete()
        print(f"Message with job_id {job_id} for users with role {user_role} deleted successfully!")


def main():
    # Add glacier connection details
    s3 = boto3.client('s3', region_name=config['aws']['AwsRegionName'], config=Config(signature_version = config['aws']['Signature']))
    glacier = boto3.client('glacier', region_name=config['aws']['AwsRegionName'])

    #Add dynamo config
    dynamodb = boto3.resource('dynamodb', region_name=config['aws']['AwsRegionName'])
    ann_table = dynamodb.Table(config['gas']['AnnotationsTable'])

    # Add SQS and queue details
    sqs_client = boto3.resource('sqs',region_name=config['aws']['AwsRegionName'])

    print(config['sqs'])
    queue = sqs_client.get_queue_by_name(QueueName=config['sqs']['SqsArchive'])
    print(f"Checking messages in {config['sqs']['SqsArchive']}")

    # Poll queue for new results and process them
    while True:
        handle_archive_queue(s3, ann_table, glacier, sqs=queue)


if __name__ == "__main__":
    main()

### EOF