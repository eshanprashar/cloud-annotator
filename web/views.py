# views.py
#
# Copyright (C) 2015-2023 Vas Vasiliadis
# University of Chicago
# Adapted for use in Genomic Annotator Service, built by Eshan Prashar, as a part of 
# graduate coursework at the University of Chicago
__author__ = "Eshan Prashar <eshanprashar@uchicago.edu>"
# Application logic for the GAS

import uuid
import time
import json
from time import strftime
from datetime import datetime
import boto3
from botocore.client import Config
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from flask import abort, flash, redirect, render_template, request, session, url_for

from app import app, db
from decorators import authenticated, is_premium

"""Start annotation request
Create the required AWS S3 policy document and render a form for
uploading an annotation input file using the policy document
"""


@app.route("/annotate", methods=["GET"])
@authenticated
def annotate():
    # Open a connection to the S3 service
    s3 = boto3.client(
        "s3",
        region_name=app.config["AWS_REGION_NAME"],
        config=Config(signature_version="s3v4"),
    )

    bucket_name = app.config["AWS_S3_INPUTS_BUCKET"]
    user_id = session["primary_identity"]

    # Generate unique ID to be used as S3 key (name)
    key_name = (
        app.config["AWS_S3_KEY_PREFIX"]
        + user_id
        + "/"
        + str(uuid.uuid4())
        + "~${filename}"
    )

    # Create the redirect URL
    redirect_url = str(request.url) + "/job"

    # Define policy conditions
    encryption = app.config["AWS_S3_ENCRYPTION"]
    acl = app.config["AWS_S3_ACL"]
    fields = {
        "success_action_redirect": redirect_url,
        "x-amz-server-side-encryption": encryption,
        "acl": acl,
        "csrf_token": app.config["SECRET_KEY"],
    }
    conditions = [
        ["starts-with", "$success_action_redirect", redirect_url],
        {"x-amz-server-side-encryption": encryption},
        {"acl": acl},
        ["starts-with", "$csrf_token", ""],
    ]

    # Generate the presigned POST call
    try:
        presigned_post = s3.generate_presigned_post(
            Bucket=bucket_name,
            Key=key_name,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=app.config["AWS_SIGNED_REQUEST_EXPIRATION"],
        )
    except ClientError as e:
        app.logger.error(f"Unable to generate presigned URL for upload: {e}")
        return abort(500)

    # Render the upload form which will parse/submit the presigned POST
    return render_template(
        "annotate.html", s3_post=presigned_post, role=session["role"]
    )


"""Fires off an annotation job
Accepts the S3 redirect GET request, parses it to extract 
required info, saves a job item to the database, and then
publishes a notification for the annotator service.
"""


@app.route("/annotate/job", methods=["GET"])
@authenticated
def create_annotation_job_request():

    region = app.config["AWS_REGION_NAME"]

    # Parse redirect URL query parameters for S3 object info
    bucket_name = request.args.get("bucket")
    s3_key = request.args.get("key")
    
    # Extract the job ID from the S3 key
    key_params = s3_key.split('/')
    cnet, user_id, input_file_params = key_params
    job_id, input_file_name = input_file_params.split('~')
    submit_time = int(time.time())
    ann_data = {
        "job_id": job_id,
        "user_id": user_id,
        "input_file_name": input_file_name,
        "s3_inputs_bucket": bucket_name,
        "s3_key_input_file": s3_key,
        "submit_time": submit_time,
        "job_status": "PENDING"
    }

    # Persist job to database
    dynamodb = boto3.resource('dynamodb',region_name=app.config["AWS_REGION_NAME"],config=Config(signature_version="s3v4"))
    ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
    ann_table.put_item(Item=ann_data)


    # Send message to request queue
    sns_client = boto3.client('sns', region_name=app.config["AWS_REGION_NAME"])
    
    # Copy data for sns but add the user role info (at the time of triggering the job)
    sns_data = ann_data.copy()
    user_role = session["role"]
    sns_data["user_role"] = user_role

    try:
        sns_client.publish(TopicArn=app.config["AWS_SNS_JOB_REQUEST_TOPIC"],Message=json.dumps(sns_data))
        message = f"{sns_data} sent to {app.config['AWS_SNS_JOB_REQUEST_TOPIC']}..Waiting to process!"
    except ClientError as e:
        message = f"Error pushing message to queue! {e}"
    print(message)
    return render_template("annotate_confirm.html", job_id=job_id)


"""List all annotations for the user
"""


@app.route("/annotations", methods=["GET"])
def annotations_list():

    # Get list of annotations to display
    # First check that the user_ID is authenticated, if not, abort with HTTP code
    if "primary_identity" not in session:
        # User is not authenticated, abort with HTTP 401 Unauthorized
        abort(401)

    # Get authenticated user_id
    user_id = session["primary_identity"]

    # Query DynamoDB table to fetch annotations for the authenticated user
    dynamodb = boto3.resource('dynamodb',region_name=app.config["AWS_REGION_NAME"],config=Config(signature_version="s3v4"))
    ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
    try:
        response = ann_table.query(
            IndexName='user_id_submit_time_index',
            KeyConditionExpression=Key('user_id').eq(user_id)
        )
        items = response['Items']
    except ClientError as e:
        # Handle DynamoDB query error
        app.logger.error(f"Failed to fetch annotations from DynamoDB: {e}")
        abort(500)

    # Extract required columns from DynamoDB items
    annotations = []
    for item in items:
        annotation = {
            'Request ID': item['job_id'],
            'Request Time': datetime.fromtimestamp(int(item['submit_time']), tz = app.config['TIMEZONE']).strftime('%Y-%m-%d @ %H:%M:%S'),
            'VCF File Name': item['input_file_name'],
            'Status': item['job_status']
        }
        annotations.append(annotation)

    # Check if any annotations were fetched
    if not annotations:
        return "No annotations found.", 200  
    return render_template("annotations.html", annotations=annotations)


"""Display details of a specific annotation job
"""


@app.route("/annotations/<id>", methods=["GET"])
@authenticated
def annotation_details(id):
    # Query DynamoDB table to fetch annotations for the authenticated user
    dynamodb = boto3.resource('dynamodb',region_name=app.config["AWS_REGION_NAME"],config=Config(signature_version="s3v4"))
    ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])
    try:
        # Source: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/dynamodb/table/get_item.html
        response = ann_table.get_item(Key={'job_id': id})
        item = response.get('Item',None)
    except ClientError as e:
        # Handle DynamoDB query error
        app.logger.error(f"Failed to fetch annotations from DynamoDB: {e}")
        abort(500)

    # Extract required columns from DynamoDB items
    if item:
        # Extract details for display
        annotation = {
            'Request ID': item['job_id'],
            'Request Time': datetime.fromtimestamp(int(item['submit_time']), tz=app.config['TIMEZONE']).strftime('%Y-%m-%d @ %H:%M:%S'),
            'VCF File Name': item['input_file_name'],
            'Status': item['job_status'],
        }
        #Generate download URL
        download_input_url = file_download_url(item['job_id'],item['input_file_name'], bucketname="AWS_S3_INPUTS_BUCKET")

        # Check user role once again and pass this to html
        user_role = session["role"]

        if item['job_status'] == 'COMPLETED':
            annotation['Complete Time'] = datetime.fromtimestamp(int(item['complete_time']), tz=app.config['TIMEZONE']).strftime('%Y-%m-%d @ %H:%M:%S')
            annotation['Annotated Log File'] = item['s3_key_log_file']
            if 's3_key_result_file' in item and item['s3_key_result_file']:  # Check if the key exists and is not empty
                annotation['Annotated Results File'] = file_download_url(item['job_id'], item['s3_key_result_file'], bucketname="AWS_S3_RESULTS_BUCKET")

    # Render the annotation details template with the extracted annotation
    return render_template("annotation.html", annotation=annotation, download_url=download_input_url, user_role=user_role)


'''
Generates signed URL to download file from s3 bucket
'''

def file_download_url(job_id, filename, bucketname):
    # Open a connection to the S3 service
    s3 = boto3.client(
        "s3",
        region_name=app.config["AWS_REGION_NAME"],
        config=Config(signature_version="s3v4"),
    )
    user_id = session["primary_identity"]
    bucket_name = app.config[bucketname]
    object_key = (
        app.config["AWS_S3_KEY_PREFIX"]
        + user_id
        + "/"
        + job_id
        + "~"
        + filename
    )

    # Generate the presigned POST call
    try:
        presigned_download_url= s3.generate_presigned_url(
            'get_object',
            Params={
            'Bucket':bucket_name,
            'Key':object_key
            },
            ExpiresIn=app.config["AWS_SIGNED_REQUEST_EXPIRATION"],
        )
        return presigned_download_url
    except ClientError as e:
        app.logger.error(f"Unable to generate presigned URL for upload: {e}")
        return abort(500)

"""Display the log file contents for an annotation job
"""

@app.route("/annotations/<id>/log", methods=["GET"])
@authenticated
def annotation_log(id):
    # Open a connection to the S3 service
    s3 = boto3.client(
        "s3",
        region_name=app.config["AWS_REGION_NAME"],
        config=Config(signature_version="s3v4"),
    )
    user_id = session["primary_identity"]
    bucket_name = app.config["AWS_S3_RESULTS_BUCKET"]
    job_id, filename = id.split('~')
    object_key = (
        app.config["AWS_S3_KEY_PREFIX"]
        + user_id
        + "/"
        + job_id
        + "~"
        + filename
    )

    # Get the object from S3
    response = s3.get_object(Bucket=bucket_name, Key=object_key)
    # Extract the content from the response
    log_content = response['Body'].read().decode('utf-8')
    return render_template("view_log.html", log_content=log_content)


"""Subscription management handler
"""
import stripe
from auth import update_profile


@app.route("/subscribe", methods=["GET", "POST"])
def subscribe():
    if request.method == "GET":
        # Fetch user details
        user_id = session["primary_identity"]
        user_role = app.config["PREMIUM_USER"] 

        # Update user role in accounts database
        update_profile(identity_id=user_id,role=user_role)

        # Update role in the session
        session["role"] = user_role

        # Request restoration of the user's data from Glacier
        # ...add code here to initiate restoration of archived user data
        # ...and make sure you handle files pending archive!

        # Establish connection with dynamo
        dynamodb = boto3.resource('dynamodb',region_name=app.config["AWS_REGION_NAME"],config=Config(signature_version="s3v4"))
        ann_table = dynamodb.Table(app.config["AWS_DYNAMODB_ANNOTATIONS_TABLE"])

        # Define sns topic for thawing
        sns_client = boto3.client('sns', region_name=app.config["AWS_REGION_NAME"])

        try:
            response = ann_table.query(
                IndexName='user_id_submit_time_index',
                KeyConditionExpression=Key('user_id').eq(user_id)
                )
            items = response['Items']
        except ClientError as e:
            # Handle DynamoDB query error
            app.logger.error(f"Failed to fetch annotations from DynamoDB: {e}")
            abort(500)

        # Extract required columns from DynamoDB items
        for item in items:
            if 'results_file_archive_id' in item and item['results_file_archive_id']:
                print(f"Archive item found {item}")
                annotation = {
                'user_id': item['user_id'],
                'archive_id': item['results_file_archive_id'], 
                'results_bucket': item['s3_results_bucket']
                }
                # Send message to request queue
                sns_data = annotation.copy()
                #user_role = session["role"]
                #sns_data["user_role"] = user_role

                # Now send message to sns thawing topic
                try:
                    sns_client.publish(TopicArn=app.config["AWS_SNS_THAWING_TOPIC"],Message=json.dumps(sns_data))
                    message = "Request sent to thawing topic for file restoration!"
                except ClientError as e:
                    message = f"Error pushing message to queue! {e}"
                print(message)
        # Render template for user
        return render_template("subscribe_confirm.html", stripe_id="forced_upgrade")
            

    elif request.method == "POST":
        # Process the subscription request

        # Create a customer on Stripe

        # Subscribe customer to pricing plan
        pass


"""DO NOT CHANGE CODE BELOW THIS LINE
*******************************************************************************
"""

"""Set premium_user role
"""


@app.route("/make-me-premium", methods=["GET"])
@authenticated
def make_me_premium():
    # Hacky way to set the user's role to a premium user; simplifies testing
    update_profile(identity_id=session["primary_identity"], role="premium_user")
    return redirect(url_for("profile"))


"""Reset subscription
"""


@app.route("/unsubscribe", methods=["GET"])
@authenticated
def unsubscribe():
    # Hacky way to reset the user's role to a free user; simplifies testing
    update_profile(identity_id=session["primary_identity"], role="free_user")
    return redirect(url_for("profile"))


"""Home page
"""


@app.route("/", methods=["GET"])
def home():
    return render_template("home.html"), 200


"""Login page; send user to Globus Auth
"""


@app.route("/login", methods=["GET"])
def login():
    app.logger.info(f"Login attempted from IP {request.remote_addr}")
    # If user requested a specific page, save it session for redirect after auth
    if request.args.get("next"):
        session["next"] = request.args.get("next")
    return redirect(url_for("authcallback"))


"""404 error handler
"""


@app.errorhandler(404)
def page_not_found(e):
    return (
        render_template(
            "error.html",
            title="Page not found",
            alert_level="warning",
            message="The page you tried to reach does not exist. \
      Please check the URL and try again.",
        ),
        404,
    )


"""403 error handler
"""


@app.errorhandler(403)
def forbidden(e):
    return (
        render_template(
            "error.html",
            title="Not authorized",
            alert_level="danger",
            message="You are not authorized to access this page. \
      If you think you deserve to be granted access, please contact the \
      supreme leader of the mutating genome revolutionary party.",
        ),
        403,
    )


"""405 error handler
"""


@app.errorhandler(405)
def not_allowed(e):
    return (
        render_template(
            "error.html",
            title="Not allowed",
            alert_level="warning",
            message="You attempted an operation that's not allowed; \
      get your act together, hacker!",
        ),
        405,
    )


"""500 error handler
"""


@app.errorhandler(500)
def internal_error(error):
    return (
        render_template(
            "error.html",
            title="Server error",
            alert_level="danger",
            message="The server encountered an error and could \
      not process your request.",
        ),
        500,
    )


"""CSRF error handler
"""


from flask_wtf.csrf import CSRFError


@app.errorhandler(CSRFError)
def csrf_error(error):
    return (
        render_template(
            "error.html",
            title="CSRF error",
            alert_level="danger",
            message=f"Cross-Site Request Forgery error detected: {error.description}",
        ),
        400,
    )


### EOF
