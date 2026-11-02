"""The pure delivery-rate rules: channels and their identities, the settings each rule reads, the precedence rule
(``policy.effective_rate``), GCRA pacing, the Smart rate controller, provider signals and SMS message parts.

Nothing here touches the database or a provider; ``..runtime`` applies these rules to the stored state.
"""
