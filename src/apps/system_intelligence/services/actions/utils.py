import json

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder

# json_safe moved into the shared safe-ORM layer; re-exported here for the old path.
from apps.core.services.db_tools.safe_orm.json import json_safe

__all__ = ["json_safe", "validation_message"]


def validation_message(exc: ValidationError) -> str:
    if hasattr(exc, "message_dict"):
        return json.dumps(exc.message_dict, cls=DjangoJSONEncoder)
    return "; ".join(exc.messages)
