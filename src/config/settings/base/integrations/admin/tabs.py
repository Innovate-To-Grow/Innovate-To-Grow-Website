"""Unfold tab groups for related models and custom admin pages."""

TABS = [
    {
        "models": [
            "core.awscredentialconfig",
            "core.gmailaccessaccount",
            "core.googlecredentialconfig",
            "core.sendverificationconfig",
        ],
        "items": [
            {"title": "AWS Credentials", "link": "/admin/core/awscredentialconfig/"},
            {"title": "Gmail Access Account", "link": "/admin/core/gmailaccessaccount/"},
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
        ],
        "items": [
            {"title": "Broadcast Email", "link": "/admin/mail/emailcampaign/"},
            {"title": "Email Log", "link": "/admin/mail/recipientlog/"},
            {"title": "Login Links", "link": "/admin/mail/loginlinktoken/"},
            {"title": "Broadcast SMS", "link": "/admin/mail/smscampaign/"},
            {"title": "SMS Log", "link": "/admin/mail/smsrecipientlog/"},
        ],
    },
    {
        "page": "mail_delivery_operations",
        "items": [
            {"title": "Delivery Dashboard", "link": "/admin/mail/delivery-dashboard/"},
            {"title": "Notification Delivery", "link": "/admin/mail/settings/"},
        ],
    },
    {
        "models": ["authn.member", "authn.membersheetsyncconfig", "authn.membersheetsynclog"],
        "items": [
            {"title": "Members", "link": "/admin/authn/member/"},
            {"title": "Member Sheet Sync", "link": "/admin/authn/membersheetsyncconfig/"},
            {"title": "Sync Logs", "link": "/admin/authn/membersheetsynclog/"},
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
    {
        "models": [
            "system_intelligence.systemintelligenceconfig",
            "system_intelligence.assistantconversationlog",
        ],
        "items": [
            {"title": "Assistant Settings", "link": "/admin/system_intelligence/systemintelligenceconfig/"},
            {"title": "Usage Dashboard", "link": "/admin/system-intelligence/usage/"},
            {"title": "Conversation Logs", "link": "/admin/system_intelligence/assistantconversationlog/"},
        ],
    },
    {
        "page": "system_intelligence_assistant_tools",
        "items": [
            {"title": "Assistant Settings", "link": "/admin/system_intelligence/systemintelligenceconfig/"},
            {"title": "Usage Dashboard", "link": "/admin/system-intelligence/usage/"},
            {"title": "Conversation Logs", "link": "/admin/system_intelligence/assistantconversationlog/"},
        ],
    },
]
