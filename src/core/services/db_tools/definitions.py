"""Bedrock tool definitions (toolSpec format) for the Converse API."""

_TOOL_DEFINITIONS = [
    {
        "toolSpec": {
            "name": "search_members",
            "description": "Search members (users) in the database by name, email, organization, or staff/active status. Returns up to 50 matching members.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Search by first or last name (partial match)"},
                        "email": {"type": "string", "description": "Search by email address (partial match)"},
                        "organization": {"type": "string", "description": "Filter by organization (partial match)"},
                        "is_staff": {"type": "boolean", "description": "Filter by staff status"},
                        "is_active": {"type": "boolean", "description": "Filter by active status"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "count_members",
            "description": "Count members in the database with optional filters.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "is_staff": {"type": "boolean", "description": "Filter by staff status"},
                        "is_active": {"type": "boolean", "description": "Filter by active status"},
                        "organization": {"type": "string", "description": "Filter by organization (partial match)"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_events",
            "description": "Search events by name, date range, or live status.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Search by event name (partial match)"},
                        "is_live": {"type": "boolean", "description": "Filter by live status"},
                        "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                        "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_event_registrations",
            "description": "Get registrations for an event. Can return the full list or just a count.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "event_name": {"type": "string", "description": "Filter by event name (partial match)"},
                        "event_id": {"type": "string", "description": "Filter by exact event UUID"},
                        "count_only": {"type": "boolean", "description": "If true, only return the count"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_projects",
            "description": "Search student projects by title, team name, organization, industry, semester, or class code.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Search by project title (partial match)"},
                        "team_name": {"type": "string", "description": "Search by team name (partial match)"},
                        "organization": {"type": "string", "description": "Filter by organization (partial match)"},
                        "industry": {"type": "string", "description": "Filter by industry (partial match)"},
                        "semester": {
                            "type": "string",
                            "description": "Filter by semester label or season (e.g. 'Spring 2025', 'Fall')",
                        },
                        "class_code": {"type": "string", "description": "Filter by class code (partial match)"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_email_campaigns",
            "description": "Search email campaigns by name, subject, or status (draft/sending/sent/failed).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Search by campaign name (partial match)"},
                        "subject": {"type": "string", "description": "Search by email subject (partial match)"},
                        "status": {
                            "type": "string",
                            "description": "Filter by status: draft, sending, sent, or failed",
                        },
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_campaign_stats",
            "description": "Get detailed delivery statistics for a specific email campaign.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "campaign_name": {"type": "string", "description": "Campaign name (partial match)"},
                        "campaign_id": {"type": "string", "description": "Exact campaign UUID"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_cms_pages",
            "description": "Search CMS pages by title, slug, or status (draft/published/archived).",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Search by page title (partial match)"},
                        "slug": {"type": "string", "description": "Search by page slug (partial match)"},
                        "status": {"type": "string", "description": "Filter by status: draft, published, or archived"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_news",
            "description": "Search news articles by title, source, or date range.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Search by article title (partial match)"},
                        "source": {"type": "string", "description": "Filter by news source (partial match)"},
                        "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                        "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_page_views",
            "description": "Get website analytics page views, optionally filtered by path or date range. Returns view counts by date and top pages.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Filter by URL path (partial match)"},
                        "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD)"},
                        "date_to": {"type": "string", "description": "End date (YYYY-MM-DD)"},
                        "count_only": {"type": "boolean", "description": "If true, only return the total count"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "get_checkin_stats",
            "description": "Get check-in statistics for events, optionally filtered by event name.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "event_name": {"type": "string", "description": "Filter by event name (partial match)"},
                        "event_id": {"type": "string", "description": "Filter by exact event UUID"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "search_semesters",
            "description": "Search academic semesters by year, season, or published status.",
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "year": {"type": "integer", "description": "Filter by year"},
                        "season": {"type": "string", "description": "Filter by season (Spring/Fall)"},
                        "is_published": {"type": "boolean", "description": "Filter by published status"},
                    },
                }
            },
        }
    },
    {
        "toolSpec": {
            "name": "run_custom_query",
            "description": (
                "Run a flexible database query against any allowed model. "
                "Available models: Member, ContactEmail, ContactPhone, Event, EventRegistration, "
                "Ticket, CheckIn, CheckInRecord, Project, Semester, EmailCampaign, RecipientLog, "
                "CMSPage, CMSBlock, NewsArticle, NewsFeedSource, PageView, Menu. "
                "Filters use Django ORM lookup syntax (e.g. name__icontains, date__gte)."
            ),
            "inputSchema": {
                "json": {
                    "type": "object",
                    "properties": {
                        "model": {"type": "string", "description": "Model name (e.g. 'Member', 'Event')"},
                        "filters": {
                            "type": "object",
                            "description": 'Django ORM filter kwargs (e.g. {"name__icontains": "demo", "is_live": true})',
                        },
                        "ordering": {
                            "description": "Field(s) to order by (string or array of strings, prefix with - for desc)",
                        },
                        "fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific fields to return (if omitted, returns all fields)",
                        },
                        "count_only": {"type": "boolean", "description": "If true, only return the count"},
                        "limit": {"type": "integer", "description": "Max rows to return (default 50, max 50)"},
                    },
                    "required": ["model"],
                }
            },
        }
    },
]


def get_tool_definitions():
    """Return the list of tool definitions for the Bedrock Converse API."""
    return list(_TOOL_DEFINITIONS)
