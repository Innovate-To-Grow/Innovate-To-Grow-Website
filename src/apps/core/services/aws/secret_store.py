"""Resolve application credentials from Secrets Manager using the ECS task identity."""

import json
import re
import time
from functools import lru_cache

import boto3
from botocore.config import Config

APPLICATION_ARN_PATTERN = (
    r"^arn:aws:secretsmanager:us-west-2:394167325273:secret:itg/backend/aws-credentials/[A-Za-z0-9/_+=.@-]+$"
)


def validate_secret_arn(arn):
    if not re.fullmatch(APPLICATION_ARN_PATTERN, arn):
        raise ValueError("Use an I2G application credential secret ARN in us-west-2.")


def read_credentials(arn):
    validate_secret_arn(arn)
    return _read_credentials(arn, int(time.monotonic() // 60))


@lru_cache(maxsize=32)
def _read_credentials(arn, window):
    # Cache only in process memory, never in Django's file/database caches.
    client = boto3.client(
        "secretsmanager",
        region_name="us-west-2",
        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 2}),
    )
    payload = json.loads(client.get_secret_value(SecretId=arn)["SecretString"])
    keys = ("access_key_id", "secret_access_key")
    if not isinstance(payload, dict) or not all(isinstance(payload.get(k), str) and payload[k].strip() for k in keys):
        raise ValueError("The AWS credential secret must contain both credential fields.")
    return payload[keys[0]], payload[keys[1]]
