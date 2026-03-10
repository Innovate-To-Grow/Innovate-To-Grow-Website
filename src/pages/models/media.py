"""Stub kept for historical migration references."""

import os


def asset_upload_path(instance, filename):
    """Upload path stub referenced by migration 0001_initial."""
    return os.path.join("pages", "media", filename)
