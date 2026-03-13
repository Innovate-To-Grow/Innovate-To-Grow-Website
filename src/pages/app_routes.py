"""
Frontend app routes available for the admin menu editor.

Single source of truth — add new pages here and they automatically
appear in the menu editor's "App Route" dropdown.
"""

APP_ROUTES = [
    # General
    {"url": "/", "title": "Home"},
    {"url": "/about", "title": "About"},
    {"url": "/news", "title": "News"},
    {"url": "/faqs", "title": "FAQs"},
    {"url": "/contact-us", "title": "Contact Us"},
    {"url": "/privacy", "title": "Privacy Policy"},
    {"url": "/ferpa", "title": "FERPA Agreement"},
    # Programs
    {"url": "/engineering-capstone", "title": "Engineering Capstone"},
    {"url": "/software-capstone", "title": "Software Capstone"},
    {"url": "/about-engsl", "title": "About Engineering Service Learning"},
    # Projects
    {"url": "/projects", "title": "Projects"},
    {"url": "/current-projects", "title": "Current Projects"},
    {"url": "/past-projects", "title": "Past Projects"},
    {"url": "/project-submission", "title": "Project Submission"},
    {"url": "/sample-proposals", "title": "Sample Proposals"},
    {"url": "/projects-teams", "title": "Projects & Teams"},
    # Students
    {"url": "/students", "title": "Students & Teams"},
    {"url": "/student-agreement", "title": "Student Agreement"},
    {"url": "/event-preparation", "title": "Event Preparation"},
    {"url": "/video-preparation", "title": "Video Preparation"},
    {"url": "/purchasing-reimbursement", "title": "Purchasing & Reimbursement"},
    # Events
    {"url": "/event", "title": "Event"},
    {"url": "/schedule", "title": "Event Schedule"},
    {"url": "/past-events", "title": "Past Events"},
    # Judging
    {"url": "/judges", "title": "Judges"},
    {"url": "/attendees", "title": "Attendees"},
    {"url": "/judging", "title": "Judging Forms"},
    # Partnerships & Sponsorship
    {"url": "/partnership", "title": "Partnership"},
    {"url": "/sponsorship", "title": "Sponsorship"},
    {"url": "/sponsor-acknowledgement", "title": "Sponsor Acknowledgement"},
    {"url": "/acknowledgement", "title": "Partners & Sponsors"},
    # Sponsor Archives
    {"url": "/sponsors/2014", "title": "2014 Sponsors"},
    {"url": "/sponsors/2015", "title": "2015 Sponsors"},
]
