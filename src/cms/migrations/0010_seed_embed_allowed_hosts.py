from django.db import migrations

SEED_HOSTS = [
    ("youtube.com", "YouTube root domain"),
    ("*.youtube.com", "YouTube subdomains (www, m, etc.)"),
    ("youtube-nocookie.com", "YouTube privacy-enhanced root"),
    ("*.youtube-nocookie.com", "YouTube privacy-enhanced subdomains"),
    ("player.vimeo.com", "Vimeo embedded player"),
    ("*.vimeo.com", "Vimeo subdomains"),
    ("docs.google.com", "Google Docs / Sheets / Slides / Forms"),
    ("forms.google.com", "Google Forms short links"),
    ("www.google.com", "Google Maps embeds"),
    ("calendly.com", "Calendly root"),
    ("*.calendly.com", "Calendly subdomains"),
    ("www.figma.com", "Figma embeds"),
    ("codesandbox.io", "CodeSandbox root"),
    ("*.codesandbox.io", "CodeSandbox subdomains"),
    ("www.typeform.com", "Typeform www"),
    ("form.typeform.com", "Typeform embedded forms"),
]


def seed_hosts(apps, schema_editor):
    Host = apps.get_model("cms", "CMSEmbedAllowedHost")
    for hostname, description in SEED_HOSTS:
        Host.objects.get_or_create(
            hostname=hostname,
            defaults={"description": description, "is_active": True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0009_cmsembedallowedhost_alter_cmsblock_block_type"),
    ]

    operations = [migrations.RunPython(seed_hosts, noop)]
