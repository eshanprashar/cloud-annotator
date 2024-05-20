# run.py
#
# Runs the AnnTools pipeline
# NOTE: This file lives on the AnnTools instance
__author__ = "Eshan Prashar <eshanprashar@uchicago.edu>"


import sys
import time
import driver
import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import json
import shutil

# Get configuration
from configparser import ConfigParser, ExtendedInterpolation

config = ConfigParser(os.environ, interpolation=ExtendedInterpolation())
config.read("annotator_config.ini")



"""A rudimentary timer for coarse-grained profiling
"""
class Timer(object):
  def __init__(self, verbose=True):
    self.verbose = verbose

  def __enter__(self):
    self.start = time.time()
    return self

  def __exit__(self, *args):
    self.end = time.time()
    self.secs = self.end - self.start
    if self.verbose:
      print(f"Approximate runtime: {self.secs:.2f} seconds")

def main():
  # Call the AnnTools pipeline
  if len(sys.argv) > 1:
    with Timer():

      # Extract sys arguments first
      input_file = sys.argv[1]
      input_key = sys.argv[2]
      input_job_id = sys.argv[3]
      input_user_id = sys.argv[4]
      input_user_role = sys.argv[5]

      # When user inputs a non-vcf format  
      try:
        driver.run(input_file, 'vcf')
      except (UnicodeDecodeError) as e:
        print(f"Error in running process because of file format! Only vcf files are supported.")

      # Setting up AWS connection
      my_config = Config(region_name=config['aws']['AwsRegionName'], signature_version = 's3v4')
      s3 = boto3.client('s3', config=my_config)

      # Adding dynamo config
      dynamodb = boto3.resource('dynamodb',config=my_config)
      ann_table = dynamodb.Table(config['gas']['AnnotationsTable'])

      # Extract the filename from the input_file
      input_file_name = os.path.basename(input_file)

      # Define the new filenames
      annot_results = input_file_name.replace('.vcf', '.annot.vcf')
      annot_logs = input_file_name.replace('.vcf', '.vcf.count.log')

      # Get the directory of the input_file
      directory = os.path.dirname(input_file)

      # Generate the full paths for the results file and log file
      annot_results_path = os.path.join(directory, annot_results)
      annot_logs_path = os.path.join(directory, annot_logs)


      # Upload results to S3
      # Error handling: Issue with the key
      try:
        key = input_key.split("~")[0]
      except (IndexError, ValueError, ClientError) as e:
        print(e)

      results_bucket = config['s3']['ResultsBucketName']

      # Source: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/s3-uploading-files.html
      try:
        s3.upload_file(annot_results_path, results_bucket, key + '~'+ annot_results)
        s3.upload_file(annot_logs_path, results_bucket, key + '~'+ annot_logs)
      except (ClientError) as e:
        print(f"Error in uploading files to S3!{e}")

      # New try-except block for uploading to Dynamo
      complete_time= int(time.time())
      # Source: https://boto3.amazonaws.com/v1/documentation/api/latest/guide/dynamodb.html
      try:
        ann_table.update_item(
          Key={
          'job_id': input_job_id
          },
          UpdateExpression= 'SET s3_results_bucket = :val1,\
          s3_key_result_file = :val2, \
          s3_key_log_file = :val3, \
          complete_time = :val4, \
          job_status = :val5',
          ExpressionAttributeValues={
          ':val1': results_bucket,
          ':val2': annot_results,
          ':val3': annot_logs,
          ':val4': complete_time,
          ':val5': 'COMPLETED'
          }
          )
      except (ClientError) as e:
        print(f"Error in updating annotator table on Dynamo! {e}")

      # Trigger step function if user is a free user
      try:
        # Source: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/stepfunctions/client/start_execution.html
        if input_user_role == "free_user":
          stepfunction = boto3.client('stepfunctions', config=my_config)
          stepfn_input_data = {
          'user_id': input_user_id,\
          'job_id': input_job_id,\
          's3_results_bucket': results_bucket,\
          's3_key_result_file': annot_results
          }
          stepfn_input = json.dumps(stepfn_input_data)
          response = stepfunction.start_execution(stateMachineArn=config['step']['ArnName'],input=stepfn_input)

      except (ClientError) as e:
        print(f"Error in updating archive SNS topic! {e}")
      
  else:
    print("The input to sub-process seems incorrect.")

  # Clean up local job irrespective of errors
  # Source: https://www.geeksforgeeks.org/python-os-rmdir-method/ (this didn't work with empty jobs folder)
  # Source: https://stackoverflow.com/questions/303200/how-do-i-remove-delete-a-folder-that-is-not-empty
  shutil.rmtree(directory)
  print(f"Jobs directory {directory} removed successfully!")

  
if __name__ == '__main__':
  main()
  

### EOF