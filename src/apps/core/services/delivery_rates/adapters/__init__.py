"""Provider adapters: what one provider answer means for the delivery rate (a ``RateSignal``).

Each reads its patterns from ``DELIVERY_RATES["signals"]`` (``rules.defaults.signal_patterns``) and only matches
provider text against them; the text itself is never stored or shown. The senders attach the signal to the error
they raise (``rate_signal``), and the email facade records it on the request's admission.
"""
