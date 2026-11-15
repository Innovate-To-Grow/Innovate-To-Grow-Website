"""Why a Broadcast SMS or a ticket text is not sent now: policy refusals made before any provider call."""

from apps.mail.models.sms_campaign import LINKS_OFF_MESSAGE


class SmsSendRefused(Exception):
    """Not sent, by policy, before any provider call; ``str()`` is the reason staff see."""


class LinksDisabled(SmsSendRefused):
    """The message has a link placeholder while links in SMS are turned off."""

    def __init__(self):
        super().__init__(LINKS_OFF_MESSAGE)


class QuietHoursActive(SmsSendRefused):
    """It is SMS quiet hours and this send cannot wait for them to end (the in-process sender)."""

    def __init__(self, until):
        self.until = until
        super().__init__(
            f"SMS quiet hours: texts can be sent again from {until:%a %H:%M %Z}. With background jobs off a "
            "campaign cannot wait for them to end, so send it then."
        )
