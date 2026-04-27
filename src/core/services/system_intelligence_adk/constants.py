import re

APP_NAME = "innovate_to_grow_system_intelligence"
AGENT_NAME = "system_intelligence"
MAX_LLM_CALLS = 24
APPROVAL_INSTRUCTION = """

Use the most specific available read tool first for members, events, projects,
CMS/layout, mail, and analytics. Use generic safe ORM tools only when the
specialized tools do not cover the question.

For any requested change to CMS content or database records, do not claim the
change is complete and do not ask the user to manually edit records. Use the
available propose_* tools to create a pending action request. Never directly
send email, trigger external sync/import jobs, change credentials/configuration,
or modify permissions/passwords/tokens. The admin UI will show an approval card,
and the change is applied only after a human approves it. For CMS page changes,
always create a preview-backed CMS page proposal.

If a requested edit is ambiguous or could modify the wrong record, ask for
confirmation before creating the proposal. Use the headings "Current state:" and
"Questions before I proceed:" so the admin UI can render the clarification as an
information card instead of a normal chat bubble. Make the choices direct:
number each option, put the action title in bold, and describe exactly what
proposal(s) will be created if the user chooses it. Do not ask the user to type
"1" or "2"; the UI will render clickable choices.
"""
PLAN_MODE_INSTRUCTION = """

PLAN MODE IS ACTIVE.

Your job in this turn is to design and refine a plan with the admin. You MUST NOT
call any propose_* or other write tools - those are unavailable in this mode.
You MAY call read-only tools (count_*, list_*, get_*, search_*) to ground your
plan in real data. Present plans as clear numbered steps. Wait for the admin to
explicitly exit plan mode before executing. Do not promise to execute on their
behalf.
"""
WRITE_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "propose_db_create",
        "propose_db_update",
        "propose_db_delete",
        "propose_cms_page_update",
        "propose_member_update",
        "propose_event_update",
        "propose_project_update",
        "propose_campaign_update",
        "propose_menu_update",
    }
)
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
