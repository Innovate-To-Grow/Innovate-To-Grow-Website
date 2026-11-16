"""Security boundaries of the legacy-view stack: ``python -m scripts.ci.legacy_infrastructure``.

``template`` loads the CloudFormation templates, ``network`` and ``cloudfront`` check their resources,
``nginx`` checks the read-only proxy configuration against the Django policy, ``cli`` runs them all.
"""
