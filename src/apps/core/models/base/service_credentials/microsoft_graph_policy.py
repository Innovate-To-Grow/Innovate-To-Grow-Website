"""A deployment-scoped decision to use OIT's provisioned app, separate from InfoSec verification.

The operator may accept one identified configuration without claiming that its Exchange isolation or broader
permissions have passed the access check. The deployment pins its identity and sole mailbox; an admin cannot
extend this policy by adding scope rows. Other configurations still need the normal go-live evidence.
"""

from django.conf import settings


def oit_provisioned_policy(config) -> dict | None:
    """Return the policy only for the saved configuration and Entra application it explicitly identifies."""
    policy = settings.GRAPH_OIT_PROVISIONED_ACTIVATION
    if not policy or config._state.adding:
        return None
    matches = (
        str(config.pk) == policy.get("config_id")
        and config.tenant_id.lower() == str(policy.get("tenant_id", "")).lower()
        and config.client_id.lower() == str(policy.get("client_id", "")).lower()
    )
    return policy if matches and policy.get("mailbox") else None


def provisioned_activation_problem(config, policy: dict) -> str:
    """Keep operator-accepted activation confined to the exact sender and one send/read mailbox scope."""
    mailbox = policy["mailbox"].strip().lower()
    if config.mailbox.strip().lower() != mailbox:
        return f"the OIT-provisioned activation policy permits only the sender mailbox {mailbox}."
    scopes = list(config.mailbox_scopes.values_list("mailbox", "permission"))
    if scopes != [(mailbox, "send_read")]:
        return f"the OIT-provisioned activation policy requires only {mailbox} with send and read scope."
    return ""
