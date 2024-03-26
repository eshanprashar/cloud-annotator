# annotator.py
#
# NOTE: This file lives on the AnnTools instance
#

import boto3
import json
import os
import sys
import time
#from subprocess import Popen, PIPE
import subprocess
from botocore.exceptions import ClientError
from botocore.config import Config

# Get configuration
from configparser import ConfigParser, ExtendedInterpolation

config = ConfigParser(os.environ, interpolation=ExtendedInterpolation())
config.read("annotator_config.ini")

# Create temp jobs folder
jobs_folder = 'jobs'


"""Reads request messages from SQS and runs AnnTools as a subprocess.
"""


# Function to create directories if they don't exist
def mkdirp(directory):
    '''
    Create a directory for a job if it doesn't exist
    '''
    if not os.path.isdir(directory):
        os.makedirs(directory)


def handle_requests_queue(s3,dynamo_table, sqs):

    # Attempt to read the maximum number of messages from the queue
    # Use long polling - DO NOT use sleep() to wait between polls
    # Added int just to make sure sqs format is honored
    messages = sqs.receive_messages(MaxNumberOfMessages=int(config['sqs']['MaxMessages']), WaitTimeSeconds=int(config['sqs']['WaitTime']))    

    # Process messages received
    if len(messages) > 0:
        print(f'Received {str(len(messages))} messages. Now processing them...')
    for message in messages:
        sns_data = message.body
        sns_parameters = json.loads(json.loads(sns_data)['Message'])
        job_id = sns_parameters['job_id']
        user_id = sns_parameters['user_id']
        filename = sns_parameters['input_file_name']
        key = sns_parameters['s3_key_input_file'] 
        bucket = sns_parameters['s3_inputs_bucket']
        user_role = sns_parameters['user_role']

        # Create a local temp folder to save job file from S3
        current_dir = os.getcwd()
        new_job_path = os.path.join(current_dir,jobs_folder,'id_'+str(job_id))
        mkdirp(new_job_path)

        # Download the file from S3 to job_ID folder
        local_path = os.path.join(new_job_path,filename)

        # Error handling: Key is not valid
        try:
            s3.download_file(bucket,key,local_path)
        except ClientError as error:
            # Handle exceptions and return an error response
            out_response = f"Key seems to invalid. {error}"
            print(out_response)

        # Launch annotation job as a background process
        # Note: Error handling for <file does not have vcf format> has been handled in run.py
        # Define path of run.py file  
        run_path = os.path.join(current_dir,"run.py")
        command = ["python", run_path, local_path, key, job_id, user_id, user_role]
        process = subprocess.Popen(command)

        # Update the Dynamo table if job status is pending
        dynamo_table.update_item(
              Key={
              'job_id': job_id
              },
              UpdateExpression= 'SET job_status = :val1',
              ConditionExpression='job_status = :val2',  
              ExpressionAttributeValues={
              ':val1':'RUNNING',
              ':val2':'PENDING'
              }
              )
        # Delete message from queue if job was successfully submitted
        message.delete()
        print(f"Message with job_id {job_id} deleted successfully!")


def main():

    # Get handles to queue
    # Add s3 connection details
    my_config = Config(region_name=config['aws']['AwsRegionName'], signature_version = 's3v4')
    s3 = boto3.client('s3', config=my_config)

    # Add dynamo config
    dynamodb = boto3.resource('dynamodb',config=my_config)
    ann_table = dynamodb.Table(config['gas']['AnnotationsTable'])

    # Add SQS and queue details
    sqs_client = boto3.resource('sqs',region_name=config['aws']['AwsRegionName'])
    queue = sqs_client.get_queue_by_name(QueueName=config['sqs']['SqsName'])
    print(f"Checking messages in {config['sqs']['SqsName']}")

    # Poll queue for new results and process them
    while True:
        handle_requests_queue(s3,ann_table,queue)


if __name__ == "__main__":
    main()

### EOF
