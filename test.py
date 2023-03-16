import boto3
import json

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

topic_arn = 'arn:aws:sns:us-west-2:394167325273:BounceNotificationsTopic'

queue_name = 'BounceNotificationsQueue'

# get my queue with the name
queue_url = sqs.get_queue_url(QueueName=queue_name)['QueueUrl']

response = sqs.get_queue_attributes(
    QueueUrl=queue_url,
    AttributeNames=['QueueArn']
)

queue_arn = response['Attributes']['QueueArn']

response = sqs.receive_message(
    QueueUrl=queue_url,
)

if 'Messages' in response:
    messages = response['Messages']
    for message in messages:
        notification = json.loads(message['Body'])
        bounce = json.loads(notification['Message'])

        email = bounce['bounce']['bouncedRecipients'][0]['emailAddress']
        diagnostic_code = bounce['bounce']['bouncedRecipients'][0]['diagnosticCode']
        
        print(email)
        print(diagnostic_code)

else:
    print('No messages in queue')
