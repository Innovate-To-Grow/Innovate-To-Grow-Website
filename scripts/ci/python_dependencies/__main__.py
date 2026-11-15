"""Entry point of ``python -m scripts.ci.python_dependencies``."""

import sys

from .cli import main

sys.exit(main())
