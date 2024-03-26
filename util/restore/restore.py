from botocore.config import Config
import boto3
import json
from botocore.exceptions import ClientError
from boto3.dynamodb.conditions import Key, Attr
import logging
import sys
import tempfile
import os

# Configure logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

# Define constants here; no config file is used for Lambdas
CNET = 'eshanprashar'
DYNAMODB_TABLE = "eshanprashar_annotations"
GAS_RESULTS_BUCKET = "gas-results"
REGION = "us-east-1"
VAULT_NAME = "ucmpcs"
#SQS_QUEUE = "eshanprashar_a16_restore"

# Initialize services
my_config = Config(region_name=REGION, signature_version = 's3v4')
s3 = boto3.client('s3', config=my_config)
glacier_client = boto3.client('glacier', region_name=REGION)
dynamodb = boto3.resource('dynamodb', region_name=REGION)
ann_table = dynamodb.Table(DYNAMODB_TABLE)


def lambda_handler(event, context):
    # Adding print statements to capture status and errors
    print("Lambda function execution started.")

    # Print the entire SNS message payload for inspection
    print(f"SNS message: {json.dumps(event)}")
    
    sns_message = json.loads(event['Records'][0]['Sns']['Message'])
    user_id = sns_message['JobDescription']
    archive_id = sns_message['ArchiveId']
    job_id = sns_message['JobId']

    
    print(f"Processing message: obtained user_id {user_id}, archive_id {archive_id} and job_id {job_id}")

    # Fetch the object from the jobId
    # Source: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/glacier/client/get_job_output.html
    thaw_response = glacier_client.get_job_output(
        vaultName=VAULT_NAME,
        jobId=job_id)

    # As an alternate measure, create temp folder and upload using put_object
    # Approach is not ideal but added due to lack of testing time
    # Create a temporary directory/file structure to download the object
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_file_path = os.path.join(tmpdir, 'downloaded_file.tmp')
        with open(tmp_file_path, 'wb') as tmp_file:
            tmp_file.write(thaw_response['body'].read())
        

    # Fetch details from dynamo using user_id
    # Connect to ann_table
    try:
        response = ann_table.query(
            IndexName='user_id_submit_time_index',
            KeyConditionExpression=Key('user_id').eq(user_id),
            FilterExpression=Attr('results_file_archive_id').eq(archive_id) 
            )
        items= response['Items']
        print(items)
        if items:
            item = items[0]  # Get the first item
            logging.info(f"Archive item found: {item}")
            job_id = item["job_id"]
            input_file = item["input_file_name"]
        else:
            print("No matching items found in DynamoDB.")

    except ClientError as e:
        print("Failed to establish connection to DynamoDB.")
        print(e)

    # Constructing the filename   
    filename = input_file.split(".")
    result_filename = filename[0] + '.annot.' + filename[1]

    # Finally constructing the S3 key
    s3_object_key =(
        CNET
        +"/"
        +user_id
        + "/"
        + job_id
        + "~"
        + result_filename
        )

    # Add logging for S3 key construction
    print(f"S3 object key constructed: {s3_object_key}")

    # Upload the file to S3
    # Source: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/upload_fileobj.html
    try:
        s3.upload_fileobj(
            Fileobj= thaw_response["body"], 
            Bucket=GAS_RESULTS_BUCKET,
            Key=s3_object_key)
        print("Object copied from Glacier to S3.") 

    except ClientError as e:
        print("Failed to upload file to S3.")
        print(e)

        # Also try upload file to s3 if upload_fileobj fails
        try:
            s3.upload_file(tmp_file_path, GAS_RESULTS_BUCKET, s3_object_key)
        except:
            print("Even upload_file failed!")


    # Update the state in DynamoDB or perform any other necessary updates
    try:
        ann_table.update_item(
            Key={'job_id': job_id},
            UpdateExpression='SET s3_key_result_file = :val1',
            ExpressionAttributeValues={
            ':val1': result_filename
            }
        )
        print(f"State updated in DynamoDB for job_id: {job_id}")
    except (ClientError) as e:
        print(f"Error in updating annotator table on DynamoDB: {e}")

    # Delete the Glacier archive
    try:
        glacier_client.delete_archive(
            vaultName=VAULT_NAME, 
            archiveId=archive_id
        )
    except ClientError as e:
        print(f"Failed to delete Glacier archive {archive_id}: {e}")

    
    print(f"Restoration completed for archive {archive_id} for user {user_id}")

    return {
        'statusCode': 200,
        'body': json.dumps('Restoration process completed successfully')}