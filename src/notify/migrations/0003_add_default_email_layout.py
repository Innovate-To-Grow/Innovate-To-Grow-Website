"""
Data migration: create the default EmailLayout.

Seeds the database with a 'base' EmailLayout whose HTML matches the
bundled ``notify/email/base.html`` template.  This lets admins customise
the layout via the admin UI without needing a deploy.
"""

from django.db import migrations

DEFAULT_LAYOUT_HTML = """\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ subject }}</title>
    <style>
      body {
        margin: 0;
        padding: 0;
        background-color: #f4f6f8;
        font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        color: #1f2933;
      }
      .preheader {
        display: none !important;
        visibility: hidden;
        opacity: 0;
        color: transparent;
        height: 0;
        width: 0;
        overflow: hidden;
      }
      .wrapper {
        width: 100%;
        background-color: #f4f6f8;
        padding: 32px 12px;
      }
      .container {
        width: 100%;
        max-width: 640px;
        background-color: #ffffff;
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #e6e8ec;
        box-shadow: 0 4px 16px rgba(15, 23, 42, 0.08);
      }
      .header {
        background-color: {{ brand_color }};
        padding: 20px 28px;
        color: #ffffff;
      }
      .brand {
        font-size: 20px;
        font-weight: 700;
        letter-spacing: 0.3px;
      }
      .logo {
        max-height: 36px;
        display: block;
      }
      .content {
        padding: 28px;
      }
      h1 {
        margin: 0 0 16px 0;
        font-size: 22px;
        line-height: 1.3;
        color: #111827;
      }
      .body {
        font-size: 15px;
        line-height: 1.7;
        color: #1f2933;
      }
      .body p {
        margin: 0 0 14px 0;
      }
      .footer {
        padding: 20px 28px 28px 28px;
        background-color: #f9fafb;
        font-size: 12px;
        color: #6b7280;
      }
      .footer a {
        color: {{ brand_color }};
        text-decoration: none;
      }
      .footer a:hover {
        text-decoration: underline;
      }
      .footer-text {
        margin-bottom: 8px;
      }
      @media (max-width: 600px) {
        .content,
        .footer,
        .header {
          padding-left: 20px;
          padding-right: 20px;
        }
        h1 {
          font-size: 20px;
        }
      }
    </style>
  </head>
  <body>
    <span class="preheader">{{ preheader }}</span>
    <table role="presentation" class="wrapper" cellspacing="0" cellpadding="0">
      <tr>
        <td align="center">
          <table role="presentation" class="container" cellspacing="0" cellpadding="0">
            <tr>
              <td class="header">
                {% if logo_url %}
                  <img src="{{ logo_url }}" alt="{{ brand_name }}" class="logo">
                {% else %}
                  <div class="brand">{{ brand_name }}</div>
                {% endif %}
              </td>
            </tr>
            <tr>
              <td class="content">
                <h1>{{ subject }}</h1>
                <div class="body">
                  {{ body_html|safe }}
                </div>
              </td>
            </tr>
            <tr>
              <td class="footer">
                {% if footer_text %}
                  <div class="footer-text">{{ footer_text }}</div>
                {% endif %}
                {% if support_email %}
                  <div><a href="mailto:{{ support_email }}">{{ support_email }}</a></div>
                {% endif %}
                {% if site_url %}
                  <div><a href="{{ site_url }}">{{ site_url }}</a></div>
                {% endif %}
                <div>&copy; {{ year }} {{ brand_name }}</div>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>\
"""


def create_default_layout(apps, schema_editor):
    EmailLayout = apps.get_model("notify", "EmailLayout")
    if not EmailLayout.objects.filter(key="base").exists():
        EmailLayout.objects.create(
            key="base",
            name="Base Layout",
            description=(
                "Default email layout with branded header, content area, and footer. "
                "Edit this in the admin to customise all outgoing emails."
            ),
            html_template=DEFAULT_LAYOUT_HTML,
            is_active=True,
            is_default=True,
        )


def remove_default_layout(apps, schema_editor):
    EmailLayout = apps.get_model("notify", "EmailLayout")
    EmailLayout.objects.filter(key="base", is_default=True).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("notify", "0002_rename_password_googlegmailaccount_google_app_password"),
    ]

    operations = [
        migrations.RunPython(create_default_layout, remove_default_layout),
    ]
