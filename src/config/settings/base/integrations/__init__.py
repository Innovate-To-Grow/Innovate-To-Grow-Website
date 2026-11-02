"""
Third-party package configuration.

  api/    – Django REST Framework and SimpleJWT.
  admin/  – Unfold theme, tab groups, sidebar navigation, and branding.
  editor/ – CKEditor 5 toolbar and plugin settings.
  credential_store/ – Private-key store backend (Secrets Manager / local file / memory) and secret names.
  microsoft_graph/ – Microsoft Graph certificate limits (key size, input size, clock skew, Entra test timeout).
  gmail_api/ – Gmail API request limits, token and assertion lifetimes, and what the admin accepts as a key.
  delivery_rates/ – Per-channel delivery-rate seeds and ceilings, the Smart rate controller, waits and signals.
"""
