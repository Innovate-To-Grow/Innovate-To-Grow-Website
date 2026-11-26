"""authn 0025: ``admin_apps`` leaves the model, but the physical column stays (with a default) for one release."""

import json

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase


class RetireAdminAppsMigrationTests(TestCase):
    def test_the_physical_column_stays_and_an_insert_without_it_succeeds(self):
        Member = get_user_model()
        table = Member._meta.db_table
        with connection.cursor() as cursor:
            columns = {column.name for column in connection.introspection.get_table_description(cursor, table)}
        self.assertIn("admin_apps", columns)
        self.assertNotIn("admin_apps", {field.name for field in Member._meta.get_fields()})

        member = Member.objects.create_user(password="StrongPass123!", first_name="New", last_name="Member")

        with connection.cursor() as cursor:
            pk = Member._meta.pk.get_db_prep_value(member.pk, connection)
            cursor.execute(f"SELECT admin_apps FROM {connection.ops.quote_name(table)} WHERE id = %s", [pk])
            (stored,) = cursor.fetchone()
        self.assertEqual(json.loads(stored) if isinstance(stored, str) else stored, [])
