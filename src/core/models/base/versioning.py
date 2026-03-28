"""Helpers for ProjectControlModel version snapshots."""

import uuid


def get_version_fields(instance):
    excluded = {"id", "created_at", "updated_at", "is_deleted", "deleted_at", "version", "versions"}
    return [
        field
        for field in instance._meta.get_fields()
        if field.name not in excluded and field.concrete and not field.many_to_many
    ]


def serialize_model_version(instance):
    data = {}
    for field in get_version_fields(instance):
        value = getattr(instance, field.name)
        if isinstance(value, uuid.UUID):
            value = str(value)
        elif hasattr(value, "pk"):
            value = str(value.pk) if value.pk else None
        data[field.name] = value
    return data


def deserialize_model_version(instance, data):
    for field in get_version_fields(instance):
        if field.name not in data:
            continue
        value = data[field.name]
        if field.is_relation and field.many_to_one:
            if value:
                related_model = field.related_model
                try:
                    value = related_model.objects.get(pk=value)
                except related_model.DoesNotExist:
                    value = None
            else:
                value = None
        setattr(instance, field.name, value)


def diff_versions(data_a, data_b):
    if data_a is None or data_b is None:
        raise ValueError("One or both versions do not exist")
    diff = {}
    for key in set(data_a.keys()) | set(data_b.keys()):
        value_a = data_a.get(key)
        value_b = data_b.get(key)
        if value_a != value_b:
            diff[key] = (value_a, value_b)
    return diff
