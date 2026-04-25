import re

APP_NAME = "innovate_to_grow_system_intelligence"
AGENT_NAME = "system_intelligence"
MAX_LLM_CALLS = 24
APPROVAL_INSTRUCTION = """

For any requested change to CMS content or database records, do not claim the
change is complete and do not ask the user to manually edit records. Use the
available propose_* tools to create a pending action request. The admin UI will
show an approval card, and the change is applied only after a human approves it.
For CMS page changes, always create a preview-backed CMS page proposal.
"""
SENTINEL = object()
TEMPERATURE_DEPRECATED_MODEL_IDS: set[str] = set()
BEDROCK_HOST_RE = re.compile(r"bedrock-runtime\.([a-z0-9-]+)\.amazonaws\.com", re.IGNORECASE)
BEDROCK_CONNECTIVITY_KEYWORDS = (
    "serviceunavailable",
    "cannot connect to host",
    "could not contact dns servers",
    "temporary failure in name resolution",
    "name or service not known",
    "nodename nor servname",
    "failed to resolve",
    "endpointconnectionerror",
)
