"""Entry point of ``python -m scripts.ci.python_quality``."""

import sys

from .cli import main

sys.exit(main())
