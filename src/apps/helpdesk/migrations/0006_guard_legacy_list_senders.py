from django.db import migrations
from django.db.models import F


def guard_legacy_list_senders(apps, schema_editor):
    # These messages predate the parser's list-address metadata. When the
    # distribution headers identified list mail, From may have been rewritten
    # to the list. Reserve that address for the existing recipient guard.
    messages = apps.get_model("helpdesk", "TicketMessage").objects.using(schema_editor.connection.alias)
    candidates = messages.filter(subtype="list", list_address="", on_behalf_of="").exclude(from_address="")
    batch = []
    for pk, signals in candidates.values_list("pk", "signals").order_by("pk").iterator(chunk_size=500):
        if not signals or {"list-id", "list-post", "precedence_list"}.intersection(signals):
            batch.append(pk)
        if len(batch) == 500:
            messages.filter(pk__in=batch).update(list_address=F("from_address"))
            batch.clear()
    if batch:
        messages.filter(pk__in=batch).update(list_address=F("from_address"))


class Migration(migrations.Migration):
    dependencies = [("helpdesk", "0005_message_on_behalf_of")]
    operations = [migrations.RunPython(guard_legacy_list_senders, migrations.RunPython.noop)]
