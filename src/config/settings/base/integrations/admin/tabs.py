"""Unfold tab groups for related models and custom admin pages."""

from .system_intelligence import SYSTEM_INTELLIGENCE_TABS

_DELIVERY_RATES_PATH = "/admin/mail/settings/rates/"

# Site Settings → Service Credentials: every provider credential, in the order Notification Delivery lists them.
SERVICE_CREDENTIAL_MODELS = (
    "core.awscredentialconfig",
    "core.smtpproviderconfig",
    "core.microsoftgraphproviderconfig",
    "core.microsoftgraphaccesscheck",
    "core.gmailapiproviderconfig",
    "core.gmailaccessaccount",
    "core.googlecredentialconfig",
    "core.sendverificationconfig",
)


def _is_notification_delivery(request):
    # Unfold marks a tab active when its link is a prefix of the path, and Delivery Rates lives under
    # /admin/mail/settings/: without this both tabs would be highlighted there.
    return request.path.startswith("/admin/mail/settings/") and not request.path.startswith(_DELIVERY_RATES_PATH)


def _helpdesk_queue_view(name):
    """Mark one ticket-list tab active; all six views share the same path."""

    def active(request):
        if not request.path.startswith("/admin/helpdesk/ticket/"):
            return False
        params = request.GET
        mail, assignee = params.get("mail", ""), params.get("assignee", "")
        if mail == "automated":
            return name == "automated"
        if params.get("sla", "") == "breached":
            return name == "breached"
        if params.get("group", "") == "mine" and not assignee:
            return name == "groups"
        return {"me": "mine", "none": "unassigned"}.get(assignee, "queue") == name

    return active


TABS = [
    {
        "models": ["helpdesk.ticket", "helpdesk.ingestrecord"],
        "items": [
            {"title": "Queue", "link": "/admin/helpdesk/ticket/", "active": _helpdesk_queue_view("queue")},
            {
                "title": "My Tickets",
                "link": "/admin/helpdesk/ticket/?assignee=me",
                "active": _helpdesk_queue_view("mine"),
            },
            {
                "title": "My Groups",
                "link": "/admin/helpdesk/ticket/?group=mine",
                "active": _helpdesk_queue_view("groups"),
            },
            {
                "title": "Unassigned",
                "link": "/admin/helpdesk/ticket/?assignee=none",
                "active": _helpdesk_queue_view("unassigned"),
            },
            {
                "title": "SLA Breached",
                "link": "/admin/helpdesk/ticket/?sla=breached",
                "active": _helpdesk_queue_view("breached"),
            },
            {
                "title": "Automated & Spam",
                "link": "/admin/helpdesk/ticket/?mail=automated&status=any",
                "active": _helpdesk_queue_view("automated"),
            },
            {"title": "Ingest Problems", "link": "/admin/helpdesk/ingestrecord/"},
        ],
    },
    {
        "models": [
            "helpdesk.ticketcategory",
            "helpdesk.assignmentgroup",
            "helpdesk.slatarget",
            "helpdesk.responsetemplate",
            {"name": "helpdesk.helpdesksettings", "detail": True},
        ],
        "items": [
            {"title": "Categories", "link": "/admin/helpdesk/ticketcategory/"},
            {"title": "Assignment Groups", "link": "/admin/helpdesk/assignmentgroup/"},
            {"title": "SLA Targets", "link": "/admin/helpdesk/slatarget/"},
            {"title": "Response Templates", "link": "/admin/helpdesk/responsetemplate/"},
            {"title": "Settings", "link": "/admin/helpdesk/helpdesksettings/"},
        ],
    },
    {
        "models": list(SERVICE_CREDENTIAL_MODELS),
        "items": [
            {"title": "AWS Credentials", "link": "/admin/core/awscredentialconfig/"},
            {"title": "SMTP", "link": "/admin/core/smtpproviderconfig/"},
            {"title": "Microsoft Graph", "link": "/admin/core/microsoftgraphproviderconfig/"},
            {"title": "Graph Access Checks", "link": "/admin/core/microsoftgraphaccesscheck/"},
            {"title": "Gmail API", "link": "/admin/core/gmailapiproviderconfig/"},
            {"title": "Gmail IMAP (Template Import)", "link": "/admin/core/gmailaccessaccount/"},
            {"title": "Google Credentials", "link": "/admin/core/googlecredentialconfig/"},
            {"title": "Send Verification", "link": "/admin/core/sendverificationconfig/"},
        ],
    },
    {
        "models": ["event.event", "event.eventregistration", "event.checkin", "event.registrationsheetsynclog"],
        "items": [
            {"title": "Events", "link": "/admin/event/event/"},
            {"title": "Registrations", "link": "/admin/event/eventregistration/"},
            {"title": "Check-ins", "link": "/admin/event/checkin/"},
            {"title": "Registration Sync Logs", "link": "/admin/event/registrationsheetsynclog/"},
        ],
    },
    {
        "models": [
            "event.currentprojectschedule",
            "event.currentproject",
            "event.schedulesynclog",
        ],
        "items": [
            {"title": "Current Projects & Schedule", "link": "/admin/event/currentprojectschedule/"},
            {"title": "Current Projects (synced)", "link": "/admin/event/currentproject/"},
            {"title": "Schedule Sync Logs", "link": "/admin/event/schedulesynclog/"},
        ],
    },
    {
        "models": ["authn.contactemail", "authn.contactphone"],
        "items": [
            {"title": "Emails", "link": "/admin/authn/contactemail/"},
            {"title": "Phones", "link": "/admin/authn/contactphone/"},
        ],
    },
    {
        "models": ["cms.newsarticle", "cms.newsfeedsource", "cms.newssynclog"],
        "items": [
            {"title": "Articles", "link": "/admin/cms/newsarticle/"},
            {"title": "Feed Sources", "link": "/admin/cms/newsfeedsource/"},
            {"title": "Sync Logs", "link": "/admin/cms/newssynclog/"},
        ],
    },
    {
        "models": ["projects.project", "projects.semester"],
        "items": [
            {"title": "Projects", "link": "/admin/projects/project/"},
            {"title": "Semesters", "link": "/admin/projects/semester/"},
        ],
    },
    {
        "models": [
            "projects.pastprojectssheetconfig",
            "projects.pastprojectshare",
            "projects.pastprojectsynclog",
        ],
        "items": [
            {"title": "Project Resources", "link": "/admin/projects/pastprojectssheetconfig/"},
            {"title": "Shared Links", "link": "/admin/projects/pastprojectshare/"},
            {"title": "Project Resource Sync Logs", "link": "/admin/projects/pastprojectsynclog/"},
        ],
    },
    {
        "models": [
            "cms.sitesettings",
            "cms.cmspage",
            "cms.cmsembedwidget",
            "cms.cmsembedallowedhost",
            "cms.menu",
            "cms.footercontent",
            "cms.stylesheet",
        ],
        "items": [
            {"title": "Home Page", "link": "/admin/cms/sitesettings/"},
            {"title": "Pages", "link": "/admin/cms/cmspage/"},
            {"title": "Embed Widgets", "link": "/admin/cms/cmsembedwidget/"},
            {"title": "Embed Allowed Hosts", "link": "/admin/cms/cmsembedallowedhost/"},
            {"title": "Menus", "link": "/admin/cms/menu/"},
            {"title": "Footer", "link": "/admin/cms/footercontent/"},
            {"title": "Style Sheets", "link": "/admin/cms/stylesheet/"},
        ],
    },
    {
        "models": [
            "mail.emailcampaign",
            "mail.recipientlog",
            "mail.loginlinktoken",
            "mail.smscampaign",
            "mail.smsrecipientlog",
            "mail.smsoptout",
            "mail.smslinktoken",
            "mail.smslinkrevocation",
            "mail.ticketsms",
            "mail.smsconfig",
        ],
        "items": [
            {"title": "Broadcast Email", "link": "/admin/mail/emailcampaign/"},
            {"title": "Email Log", "link": "/admin/mail/recipientlog/"},
            {"title": "Login Links", "link": "/admin/mail/loginlinktoken/"},
            {"title": "Broadcast SMS", "link": "/admin/mail/smscampaign/"},
            {"title": "SMS Log", "link": "/admin/mail/smsrecipientlog/"},
            {"title": "SMS Opt-outs", "link": "/admin/mail/smsoptout/"},
            {"title": "SMS Links", "link": "/admin/mail/smslinktoken/"},
            {"title": "Ticket SMS", "link": "/admin/mail/ticketsms/"},
            {"title": "SMS Settings", "link": "/admin/mail/smsconfig/"},
        ],
    },
    {
        # Email Monitoring holds every delivery figure: its tabs are Overview, Email log, Bounce reports, Bounced
        # addresses and Amazon SES (the former Delivery Dashboard, whose old address redirects there). Unfold marks
        # this tab active on every page under its link.
        "page": "mail_delivery_operations",
        "items": [
            {"title": "Email Monitoring", "link": "/admin/mail/email-monitoring/"},
            {"title": "Notification Delivery", "link": "/admin/mail/settings/", "active": _is_notification_delivery},
            {"title": "Delivery Rates", "link": _DELIVERY_RATES_PATH},
        ],
    },
    {
        "models": [
            "authn.member",
            "authn.membersheetsyncconfig",
            "authn.membersheetsynclog",
            "authn.memberimportbatch",
        ],
        "items": [
            {"title": "Members", "link": "/admin/authn/member/"},
            {"title": "Member Sheet Sync", "link": "/admin/authn/membersheetsyncconfig/"},
            {"title": "Sync Logs", "link": "/admin/authn/membersheetsynclog/"},
            {"title": "Member Imports", "link": "/admin/authn/memberimportbatch/"},
        ],
    },
    {
        "models": [
            "cli_admin.cliaccesstoken",
            "cli_admin.cliauthorizationcode",
            "cli_admin.cliauditlog",
        ],
        "items": [
            {"title": "Access Tokens", "link": "/admin/cli_admin/cliaccesstoken/"},
            {"title": "Authorization Codes", "link": "/admin/cli_admin/cliauthorizationcode/"},
            {"title": "Audit Log", "link": "/admin/cli_admin/cliauditlog/"},
        ],
    },
    *SYSTEM_INTELLIGENCE_TABS,
]
