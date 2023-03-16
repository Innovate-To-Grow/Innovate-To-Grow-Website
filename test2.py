import boto3
import json
import time

aws_access_key_id = "***REMOVED_AWS_KEY_ID***"
aws_secret_access_key = "***REMOVED_AWS_SECRET***"

ses = boto3.client('ses',
                   region_name='us-west-2',
                   aws_access_key_id=aws_access_key_id,
                   aws_secret_access_key=aws_secret_access_key)

sns = boto3.client('sns',
                   region_name='us-west-2',
                   aws_access_key_id=aws_access_key_id,
                   aws_secret_access_key=aws_secret_access_key)

sqs = boto3.client('sqs',
                   region_name='us-west-2',
                   aws_access_key_id=aws_access_key_id,
                   aws_secret_access_key=aws_secret_access_key)

# specify the URL of the SQS queue
queue_url = 'https://sqs.us-west-2.amazonaws.com/394167325273/BounceNotificationsQueue'

ses.send_email(
    Destination={
        'ToAddresses': [
            'test@gmail.com',
        ],
    },
    Message={
        'Body': {
            'Text': {
                'Charset': 'UTF-8',
                'Data': 'This is the message body in text format.',
            },
        },
        'Subject': {
            'Charset': 'UTF-8',
            'Data': 'Test email',
        },
    },
    Source="Innovate to Grow - UC Merced <i2g@g.ucmerced.edu>",
)