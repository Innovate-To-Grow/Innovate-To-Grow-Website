"""Django-app dependency directions and import cycles: ``python -m scripts.ci.python_dependencies``.

``cli`` runs the check, ``imports`` resolves every module's imports, ``rules`` applies
``python_dependencies.toml``, ``cycles`` finds strongly connected components.
"""
