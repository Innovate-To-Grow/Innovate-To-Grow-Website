"""CMS seed data for home."""

PAGE = {
    "slug": "home",
    "route": "/",
    "title": "Home",
    "page_css_class": "home-page",
    "blocks": [
        {
            "block_type": "rich_text",
            "sort_order": 0,
            "admin_label": "Homepage content",
            "data": {
                "heading": "Innovate to Grow",
                "heading_level": 1,
                "body_html": '<div class="home-hero"><p class="home-hero-subtitle">UC Merced School of Engineering\'s Experiential Learning Program</p></div><div class="home-quick-links"><a href="/project-submission" class="home-btn home-btn-gold">Submit a Project</a><a href="/about" class="home-btn home-btn-blue">Learn More</a><a href="/news" class="home-btn home-btn-gold">News</a></div><div class="home-about"><h2 class="home-section-title">Engineering Solutions for Innovative Organizations</h2><p class="home-text">Innovate to Grow (I2G) is a unique &quot;experiential learning&quot; program that engages external partner organizations with teams of students who design systems to solve complex, real-world problems. At the end of each semester, the work completed by the student teams culminates in the Innovate to Grow event.</p><div class="home-cta-row"><a href="/partnership" class="home-link">Partnership Opportunities</a><a href="/sponsorship" class="home-link">Sponsorship</a><a href="/faqs" class="home-link">FAQs</a></div></div><div class="home-event-info"><h2 class="home-section-title">Event</h2><div class="home-event-links"><a href="/event">Event Details</a><a href="/schedule">Full Schedule</a><a href="/projects-teams">All Projects &amp; Teams</a><a href="/judges">Judge Info</a><a href="/attendees">Attendee Info</a></div></div>',
            },
        }
    ],
}
