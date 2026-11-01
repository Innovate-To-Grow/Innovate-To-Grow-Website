"""Copy credentials to Secrets Manager, then separately retire database plaintext."""

import json

import boto3
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.core.models import AWSCredentialConfig
from apps.core.services.aws.secret_store import validate_secret_arn


class Command(BaseCommand):
    help = "Migrate AWS credentials without printing them. Clear plaintext only after rollout."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear-legacy", action="store_true", help="Verify the cloud copy before clearing database keys."
        )

    def handle(self, *args, **options):
        client = boto3.client("secretsmanager", region_name="us-west-2")
        count = 0
        for pk in AWSCredentialConfig.objects.values_list("pk", flat=True):
            try:
                with transaction.atomic():
                    config = AWSCredentialConfig.objects.select_for_update().get(pk=pk)
                    self._migrate(client, config, options["clear_legacy"])
                    count += 1
            except Exception:
                # Provider responses and local variables must not leak key material.
                raise CommandError(
                    f"Credential migration failed for config {pk}; database keys were preserved."
                ) from None
        self.stdout.write(f"Verified {count} AWS credential configurations; clear_legacy={options['clear_legacy']}.")

    def _migrate(self, client, config, clear):
        legacy = {"access_key_id": config.access_key_id, "secret_access_key": config.secret_access_key}
        has_legacy = any(legacy.values())
        if has_legacy and not all(legacy.values()):
            raise ValueError("Incomplete legacy credentials")
        arn = config.credentials_secret_arn
        if not has_legacy and not arn:
            if config.is_active:
                raise ValueError("Active credential configuration is empty")
            return
        if not arn:
            if clear:
                raise ValueError("Copy phase must finish before clearing credentials")
            name = f"itg/backend/aws-credentials/{config.pk}"
            try:
                result = client.create_secret(
                    Name=name,
                    SecretString=json.dumps(legacy),
                    Description="I2G application credentials for SES, SNS, Bedrock and usage metrics.",
                    Tags=[
                        {"Key": "Project", "Value": "I2G"},
                        {"Key": "Environment", "Value": "prod"},
                        {"Key": "Purpose", "Value": "application-aws-credentials"},
                    ],
                )
                arn = result["ARN"]
            except client.exceptions.ResourceExistsException:
                arn = client.get_secret_value(SecretId=name)["ARN"]
        validate_secret_arn(arn)
        stored = json.loads(client.get_secret_value(SecretId=arn)["SecretString"])
        if not all(isinstance(stored.get(k), str) and stored[k].strip() for k in legacy):
            raise ValueError("Incomplete cloud credentials")
        if has_legacy and any(stored[k] != v for k, v in legacy.items()):
            raise ValueError("Cloud and database credentials differ; refusing to overwrite either")
        updates = {"credentials_secret_arn": arn, "updated_at": timezone.now()}
        if clear:
            updates.update(access_key_id="", secret_access_key="")
        AWSCredentialConfig.objects.filter(pk=config.pk).update(**updates)
