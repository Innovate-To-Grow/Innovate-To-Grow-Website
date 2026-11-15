"""The provider-neutral sending path every email provider shares: the message and result contracts, the
delivery facade (rate admission, provider resolution, telemetry), the failure taxonomy, MIME generation, the
provider registry, and the bounded HTTPS transport for the fixed endpoints the Graph and Gmail API providers call.
"""
