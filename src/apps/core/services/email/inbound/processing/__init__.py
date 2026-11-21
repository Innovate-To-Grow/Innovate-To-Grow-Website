"""The inbound queue's rows: recording listed messages and their retention (``queue``), a consumer claiming and
settling them (``consume``), removing personal sign-in links before anything is stored (``scrub``, which reads a link
a mail-security gateway wrapped by the link it holds: ``gateways``), and the apps that list the Inbox on their own
schedule (``registry``).
"""
