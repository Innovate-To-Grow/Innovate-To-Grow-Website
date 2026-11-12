"""The tables the bounce classifier (``bounces.classify``) reads.

- ``codes``: the enhanced status codes that decide a category on their own, the generic ones the diagnostic text may
  refine, what a code means when nothing more specific names it, and the reason shown for a code.
- ``phrases``: the diagnostic phrases that refine a generic code (or a report without one).

**Specific codes always win**: no phrase turns a ``5.1.1`` into a spam rejection, or an expired delivery into a
missing address; a code servers use for more than one thing (``codes.AMBIGUOUS``) may only be made temporary. A
temporary ``4.x.x`` failure is never a missing address or a disabled mailbox. Tune the phrases against the real
diagnostics on Email Monitoring → Bounce Reports.
"""
