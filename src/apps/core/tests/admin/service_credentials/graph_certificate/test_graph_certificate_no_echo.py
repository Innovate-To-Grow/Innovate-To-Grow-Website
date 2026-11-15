"""The private key and the .p12 / PEM password never leave the install request.

After every install (accepted or refused), rollback and remove, nothing an admin or a later request can read holds
a 32-character slice of the submitted key or the password: the response pages, the session rows, the messages
cookie, anything written to a cache, the admin history, every log record (all loggers at DEBUG, SQL included),
the Graph tables, and the text of every exception the parsing and install code raised.
"""

import contextlib
import logging

CACHE_WRITES = ("set", "add", "set_many", "get_or_set")


def key_slices(*texts):
    """32-character slices of every base64 line of each submitted key text (what a leak would contain)."""
    slices = []
    for text in texts:
        lines = [line for line in text.splitlines() if line and not line.startswith(("-----", "Proc-Type", "DEK-"))]
        slices.extend(line[:32] for line in lines if len(line) >= 32)
    return slices


class _Records(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.DEBUG)
        self.text = []

    def emit(self, record):
        self.text.append(logging.Formatter().format(record))
        self.text.append(repr(record.__dict__))


@contextlib.contextmanager
def every_log_record():
    """Attach one handler to every logger at DEBUG (restoring levels after), so nothing is filtered out."""
    handler = _Records()
    loggers = [logging.getLogger()] + [
        logger for logger in logging.root.manager.loggerDict.values() if isinstance(logger, logging.Logger)
    ]
    saved = [(logger, logger.level, logger.disabled) for logger in loggers]
    for logger in loggers:
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.disabled = False
    try:
        yield handler.text
    finally:
        for logger, level, disabled in saved:
            logger.removeHandler(handler)
            logger.setLevel(level)
            logger.disabled = disabled
