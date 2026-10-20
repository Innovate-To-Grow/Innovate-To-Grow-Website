"""Style the signed-in account button for its new label.

The header's account button now reads the member's name (or email) instead of "My Account".
This adds a block to the CMS-managed "layout-menu" sheet that drops its underline and cuts a
long label with an ellipsis. The block is appended (an admin's other edits to the sheet are
kept) and only once; data/stylesheets.json carries the same block for new databases. The
reverse removes it.
"""

from django.db import migrations

SHEET = "layout-menu"
MARKER = "/* Signed-in account button: the member's name or email"

BLOCK = """
/* Signed-in account button: the member's name or email, not underlined; a long one ends
   in an ellipsis (the full label is its title). */
.member-button {
  text-decoration: none;
}

.member-label {
  max-width: 16rem;
  overflow: hidden;
  text-overflow: ellipsis;
}
"""


def add_block(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")
    sheet = StyleSheet.objects.filter(name=SHEET).first()
    if sheet is None or MARKER in sheet.css:
        return
    sheet.css = sheet.css.rstrip("\n") + "\n" + BLOCK
    sheet.save(update_fields=["css"])


def remove_block(apps, schema_editor):
    StyleSheet = apps.get_model("cms", "StyleSheet")
    sheet = StyleSheet.objects.filter(name=SHEET).first()
    if sheet is None or BLOCK not in sheet.css:
        return
    sheet.css = sheet.css.replace("\n" + BLOCK, "\n").replace(BLOCK, "")
    sheet.save(update_fields=["css"])


class Migration(migrations.Migration):
    dependencies = [
        ("cms", "0023_acknowledgement_cms_page"),
    ]

    operations = [
        migrations.RunPython(add_block, remove_block),
    ]
