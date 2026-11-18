"""Invalidate old SES recommendations that treated every permanent bounce as a missing mailbox."""


def refresh_link_summaries(apps, schema_editor):
    Address = apps.get_model("mail", "BouncedAddress")
    Link = apps.get_model("mail", "BouncedAddressCampaign")
    db = schema_editor.connection.alias
    links = Link.objects.using(db).filter(source="ses").values("bounced_address_id")
    # Historical SES summaries have no review_counts. The bounded staff/worker refresh fills them from
    # retained campaign links, including when their original recipient logs are no longer available.
    Address.objects.using(db).filter(pk__in=links, suggestion__in=("undeliverable", "consider")).update(suggestion="")
