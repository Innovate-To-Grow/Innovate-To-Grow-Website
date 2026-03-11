"""
Frontend app routes available for the admin menu editor.

Single source of truth — add new pages here and they automatically
appear in the menu editor's "App Route" dropdown.
"""

APP_ROUTES = [
    {"url": "/", "title": "Home", "icon": "fa-home"},
    {"url": "/about", "title": "About", "icon": "fa-info-circle"},
    {"url": "/engineering-capstone", "title": "Engineering Capstone", "icon": "fa-cogs"},
    {"url": "/software-capstone", "title": "Software Capstone", "icon": "fa-code"},
    {"url": "/news", "title": "News", "icon": "fa-newspaper-o"},
    {"url": "/projects", "title": "Projects", "icon": "fa-folder-open"},
    {"url": "/current-projects", "title": "Current Projects", "icon": "fa-briefcase"},
    {"url": "/past-projects", "title": "Past Projects", "icon": "fa-archive"},
    {"url": "/project-submission", "title": "Project Submission", "icon": "fa-paper-plane"},
    {"url": "/sample-proposals", "title": "Sample Proposals", "icon": "fa-file-text-o"},
    {"url": "/students", "title": "Students & Teams", "icon": "fa-users"},
    {"url": "/student-agreement", "title": "Student Agreement", "icon": "fa-handshake-o"},
    {"url": "/event-preparation", "title": "Event Preparation", "icon": "fa-calendar-check-o"},
    {"url": "/video-preparation", "title": "Video Preparation", "icon": "fa-video-camera"},
    {"url": "/purchasing-reimbursement", "title": "Purchasing & Reimbursement", "icon": "fa-credit-card"},
    {"url": "/ferpa", "title": "FERPA Agreement", "icon": "fa-file-text"},
]
