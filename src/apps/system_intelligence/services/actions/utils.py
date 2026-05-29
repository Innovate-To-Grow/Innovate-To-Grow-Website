import json
from typing import Any

from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder, default=str))


def validation_message(exc: ValidationError) -> str:
    if hasattr(exc, "message_dict"):
        return json.dumps(exc.message_dict, cls=DjangoJSONEncoder)
    return "; ".join(exc.messages)
