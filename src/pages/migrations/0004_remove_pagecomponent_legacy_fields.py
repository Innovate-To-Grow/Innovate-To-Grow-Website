"""
Step 3: Remove legacy page/home_page/order fields from PageComponent,
along with their constraints and indexes.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pages", "0003_populate_placements"),
    ]

    operations = [
        # Update Meta options
        migrations.AlterModelOptions(
            name="pagecomponent",
            options={
                "ordering": ["id"],
                "verbose_name": "Page Component",
                "verbose_name_plural": "Page Components",
            },
        ),
        # Remove old constraints
        migrations.RemoveConstraint(
            model_name="pagecomponent",
            name="pages_pagecomponent_single_parent",
        ),
        migrations.RemoveConstraint(
            model_name="pagecomponent",
            name="uniq_component_order_per_page",
        ),
        migrations.RemoveConstraint(
            model_name="pagecomponent",
            name="uniq_component_order_per_homepage",
        ),
        # Remove old indexes
        migrations.RemoveIndex(
            model_name="pagecomponent",
            name="pages_pagec_page_id_3dc713_idx",
        ),
        migrations.RemoveIndex(
            model_name="pagecomponent",
            name="pages_pagec_home_pa_52f8ea_idx",
        ),
        # Remove old fields
        migrations.RemoveField(
            model_name="pagecomponent",
            name="home_page",
        ),
        migrations.RemoveField(
            model_name="pagecomponent",
            name="order",
        ),
        migrations.RemoveField(
            model_name="pagecomponent",
            name="page",
        ),
    ]
