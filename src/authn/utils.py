"""
Shared utility helpers for the authn app.
"""

import uuid


def generate_unique_username(email: str) -> str:
    """Generate a unique username from an email address using a UUID suffix.

    Instead of a while-loop that queries the database on each iteration,
    this appends a short random hex suffix that is statistically unique.
    """
    base = email.split("@", 1)[0]
    return f"{base}_{uuid.uuid4().hex[:8]}"
