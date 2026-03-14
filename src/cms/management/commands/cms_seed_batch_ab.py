"""Seed CMS pages for Batch A (simple) and Batch B (rich content) pages."""

from django.core.management.base import BaseCommand

from cms.models import CMSBlock, CMSPage

SEED_PAGES = [
    # ==================== BATCH A ====================
    {
        "slug": "partnership",
        "route": "/partnership",
        "title": "Partnership Opportunities",
        "page_css_class": "partnership-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Partnership intro",
                "data": {
                    "heading": "Partnership Opportunities",
                    "heading_level": 1,
                    "body_html": (
                        '<h2 class="partnership-section-title">Thank you for your Support!</h2>'
                        '<p class="partnership-text">'
                        "If you would like to be a part of the exciting programming offered by the "
                        "School of Engineering (the Innovate to Grow event or our &quot;experiential "
                        "learning&quot; Engineering Capstone, Software Engineering Capstone, and "
                        "Engineering Service Learning classes), consider participating in one of the "
                        "following ways listed below:"
                        "</p>"
                        '<ul class="partnership-list">'
                        '<li><a href="/project-submission">Propose / mentor a project</a></li>'
                        '<li><a href="/judges">Sign up to Judge</a></li>'
                        '<li><a href="/sponsorship">Sponsor the program or event</a></li>'
                        '<li><a href="/faqs">FAQs</a></li>'
                        "</ul>"
                        '<p class="partnership-text">'
                        "For further information or if you have any questions, please contact us at "
                        'email <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.'
                        "</p>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "purchasing-reimbursement",
        "route": "/purchasing-reimbursement",
        "title": "Capstone Purchasing & Reimbursement",
        "page_css_class": "student-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Purchasing forms",
                "data": {
                    "heading": "Capstone Purchasing & Reimbursement",
                    "heading_level": 1,
                    "body_html": (
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Capstone Purchasing Forms</h2>'
                        '<p class="student-text">Forms are dependent on the class.</p>'
                        '<ul class="student-list">'
                        "<li>"
                        '<a href="https://soeinstructional.ucmerced.edu/capstone-design/capstone-purchase-request-form-ce-193-dr-robert-rice" '
                        'target="_blank" rel="noopener noreferrer">'
                        "Capstone Purchase Request Form - CE 193</a></li>"
                        "<li>"
                        '<a href="https://soeinstructional.ucmerced.edu/capstone-design/capstone-purchase-request-form-cse-120-dr-santosh-chandrasekhar" '
                        'target="_blank" rel="noopener noreferrer">'
                        "Capstone Purchase Request Form - CSE 120</a></li>"
                        "<li>"
                        '<a href="https://soeinstructional.ucmerced.edu/capstone-design/capstone-purchase-request-form-engr-193-dr-alejandro-guti%C3%A9rrez" '
                        'target="_blank" rel="noopener noreferrer">'
                        "Capstone Purchase Request Form - ENGR 193</a></li>"
                        "<li>"
                        '<a href="https://soeinstructional.ucmerced.edu/capstone-design/capstone-purchase-request-form-engr-194-dr-alejandro-guti%C3%A9rrez" '
                        'target="_blank" rel="noopener noreferrer">'
                        "Capstone Purchase Request Form - ENGR 194</a></li>"
                        "</ul>"
                        '<p class="student-text">'
                        "For more information, please visit the "
                        '<a href="https://soeinstructional.ucmerced.edu/capstone-design" '
                        'target="_blank" rel="noopener noreferrer">'
                        "SoE-Instructional site for Capstone</a>.</p>"
                        "</section>"
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Reimbursement for Travel and Small Expenses</h2>'
                        '<p class="student-text">'
                        "To submit a request for reimbursement, please first read the instructions "
                        "provided in your class announcements and the guidelines below, and submit "
                        "this form when the information is correct and complete:</p>"
                        '<ul class="student-list">'
                        '<li><a href="https://forms.gle/AKgT3CcRLoKBa6W8A" target="_blank" '
                        'rel="noopener noreferrer">I2G-Capstone-Reimbursement Form</a></li>'
                        '<li><a href="https://drive.google.com/file/d/1pexXU8lxx6-_j5iiMxUtDb5oCGZjiXWP/view?usp=sharing" '
                        'target="_blank" rel="noopener noreferrer">'
                        "Guidelines for Travel and Small Expenses Reimbursements for Teams in I2G / Capstone</a></li>"
                        "</ul>"
                        '<p class="student-text">'
                        "<strong>All teams</strong> (the student in charge of finance / CFO) that "
                        "need to purchase materials or get reimbursed for travel "
                        '<strong><a href="https://drive.google.com/file/d/1pexXU8lxx6-_j5iiMxUtDb5oCGZjiXWP/view?usp=sharing" '
                        'target="_blank" rel="noopener noreferrer">MUST READ these guidelines</a></strong> '
                        "before entering any forms.</p>"
                        "</section>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "students",
        "route": "/students",
        "title": "Students & Teams",
        "page_css_class": "student-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Students intro",
                "data": {
                    "heading": "Students & Teams - Resources for I2G Projects and Events",
                    "heading_level": 1,
                    "body_html": (
                        '<p class="student-text">'
                        "This section contains information and guidelines for students and teams participating in:</p>"
                        '<ul class="student-list">'
                        "<li>An I2G project, such as Eng. Capstone and Software Engineering</li>"
                        "<li>The I2G event and showcase</li>"
                        "</ul>"
                    ),
                },
            },
            {
                "block_type": "navigation_grid",
                "sort_order": 1,
                "admin_label": "Student resource links",
                "data": {
                    "items": [
                        {
                            "title": "I2G Project - Student Agreement",
                            "description": "The template of the agreement that a student must sign to participate in any project provided and sponsored by partner organizations. The agreement is digitally signed by acceptance in the survey to view and participate in projects at the beginning of the semester.",
                            "url": "/student-agreement",
                            "is_external": False,
                        },
                        {
                            "title": "FERPA Agreement",
                            "description": "The template of the agreement that a student must sign to participate in the Innovate to Grow event, allowing to record and distribute presentations and videos (media waiver).",
                            "url": "/ferpa",
                            "is_external": False,
                        },
                        {
                            "title": "Video Presentations",
                            "description": "Guidelines and instructions to prepare video presentations. Contains several general guidelines useful for any professional video presentation, particularly in engineering, with some details specific to Capstone and I2G.",
                            "url": "/video-preparation",
                            "is_external": False,
                        },
                        {
                            "title": "I2G Event Preparation",
                            "description": "Information on I2G and instructions for students and teams to plan for it pre- during- and post-event.",
                            "url": "/event-preparation",
                            "is_external": False,
                        },
                        {
                            "title": "Purchasing / Travel / Expense Reimbursements",
                            "description": "Guidelines and forms for purchasing and travel reimbursement.",
                            "url": "/purchasing-reimbursement",
                            "is_external": False,
                        },
                        {
                            "title": "Student Experience Survey",
                            "description": "Fill this survey for feedback and comments on the Capstone - I2G project, and event experience.",
                            "url": "https://ucmerced.az1.qualtrics.com/jfe/form/SV_e4L1PyHidYuThEW",
                            "is_external": True,
                        },
                    ],
                },
            },
        ],
    },
    {
        "slug": "past-events",
        "route": "/past-events",
        "title": "Past Events",
        "page_css_class": "past-events-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Intro text",
                "data": {
                    "heading": "Past Events",
                    "heading_level": 1,
                    "body_html": (
                        '<p class="past-events-page-text">'
                        "The Innovate to Grow event has been held every semester since Fall 2012, "
                        "showcasing UC Merced student innovation in engineering and computer science. "
                        "Browse the archive of past events below to see the teams, projects, and "
                        "schedules from previous semesters.</p>"
                    ),
                },
            },
            {
                "block_type": "link_list",
                "sort_order": 1,
                "admin_label": "Event archive links",
                "data": {
                    "heading": "Event Archive",
                    "style": "list",
                    "items": [
                        {"label": "Fall 2025", "url": "/events/2025-fall", "is_external": False},
                        {"label": "Spring 2025", "url": "/events/2025-spring", "is_external": False},
                        {"label": "Fall 2024", "url": "/events/2024-fall", "is_external": False},
                        {"label": "Spring 2024", "url": "/events/2024-spring", "is_external": False},
                        {"label": "Fall 2023", "url": "/events/2023-fall", "is_external": False},
                        {"label": "Spring 2023", "url": "/events/2023-spring", "is_external": False},
                        {"label": "Fall 2022", "url": "/events/2022-fall", "is_external": False},
                        {"label": "Spring 2022", "url": "/events/2022-spring", "is_external": False},
                        {"label": "Fall 2021", "url": "/events/2021-fall", "is_external": False},
                        {"label": "Spring 2021", "url": "/events/2021-spring", "is_external": False},
                        {"label": "Fall 2020", "url": "/events/2020-fall", "is_external": False},
                    ],
                },
            },
        ],
    },
    # ==================== BATCH B ====================
    {
        "slug": "about",
        "route": "/about",
        "title": "About",
        "page_css_class": "about-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "About content",
                "data": {
                    "heading": "Engineering Solutions for Innovative Organizations",
                    "heading_level": 1,
                    "body_html": (
                        '<p class="about-lead">'
                        "Innovate to Grow (I2G) is a unique &quot;experiential learning&quot; program "
                        "that engages external partner organizations with teams of students who design "
                        "systems to solve complex, real-world problems.</p>"
                        '<p class="about-text">'
                        "At the end of each semester, the work completed by the student teams "
                        "culminates in the Innovate to Grow event, which features student-led research "
                        "and highlights their project outcomes. The bi-annual Innovate to Grow event "
                        "is a showcase of UC Merced student ingenuity and creativity, and the marquee "
                        "event for the School of Engineering, drawing hundreds of industry leaders, "
                        "community members, and entrepreneurs from the Central Valley, Silicon Valley, "
                        "Southern California and beyond.</p>"
                        '<p class="about-text">'
                        "Innovate to Grow began in 2012 as the culminating event for the School of "
                        "Engineering's Senior Capstone teams' final report, originating from an idea "
                        "first sketched on a napkin by then\u2013Dean Dan Hirleman. Since then, the "
                        "Innovate to Grow program has evolved to encompass the following experiential "
                        "learning classes and key threads of our campus's innovation culture:</p>"
                        '<ul class="about-list">'
                        "<li>"
                        '<a href="https://i2g.ucmerced.edu/engineering-capstone" target="_blank" rel="noopener noreferrer">'
                        "Engineering Capstone</a> - CAP (formerly known as Innovation Design Clinic)</li>"
                        "<li>"
                        '<a href="https://i2g.ucmerced.edu/software-capstone" target="_blank" rel="noopener noreferrer">'
                        "Software Engineering Capstone</a> - CSE (formerly known as Mobile App Challenge, MAC)</li>"
                        "<li>Civil &amp; Environmental Engineering Capstone - CEE</li>"
                        "<li>"
                        '<a href="https://engineeringservicelearning.ucmerced.edu/" target="_blank" rel="noopener noreferrer">'
                        "Engineering Service Learning</a> - ESL</li>"
                        "</ul>"
                        '<p class="about-text">'
                        "In one year (two semesters) the Innovate to Grow projects, classes, and "
                        "events involve approximately 500 students and 100 teams. The classes that are "
                        "part of the Innovate to Grow program have grown since its inception, as our "
                        "enrollments in engineering and computer science continue to grow rapidly.</p>"
                        '<p class="about-text">'
                        "Depending on the nature of the project, the amenability for multiple solutions "
                        "or competition and the availability and interest of the industry mentors, a "
                        "team may be paired 1:1 with a partner/project, while other projects have two "
                        "or more teams competing to produce competitive designs.</p>"
                        '<p class="about-text">'
                        "The projects tackled by the students involve a variety of industries, such as "
                        "Agriculture, Food Processing, Water, Energy, Health Care, Medical Devices, "
                        "Finance, Transportation, Construction, Materials, IT, Networking, and more.</p>"
                        '<p class="about-text">'
                        "Most student innovations are related to projects inspired by industry partners "
                        "and community organizations where success might be measured by:</p>"
                        '<ul class="about-list">'
                        "<li>a system or process improvement for the partner's operations or plant;</li>"
                        "<li>a prototype or invention that may lead to a product or patent application;</li>"
                        "<li>a software application or system improvement;</li>"
                        "<li>studies and prototypes for government labs or nonprofits in the local community.</li>"
                        "</ul>"
                        '<p class="about-text">'
                        "Some of those innovations can help, or turn into, small businesses in the "
                        "community. The innovation and entrepreneurial thinking embedded in our culture "
                        "are signatures of our programs and highlight the unique student experience for "
                        "undergraduate students on our campus.</p>"
                        '<p class="about-text">Please see more details if you are interested in partnering with us:</p>'
                        '<ul class="about-list">'
                        '<li>You may <a href="https://i2g.ucmerced.edu/partnership" target="_blank" rel="noopener noreferrer">sponsor</a> '
                        "the program and events.</li>"
                        '<li>You may <a href="/project-submission">propose a project</a> that can be evaluated for fit in '
                        "Engineering Capstone, Software Engineering Capstone, or Service Learning, or an internship, or "
                        "potentially collaborative research with Faculty at UC Merced.</li>"
                        '<li>You may search all <a href="/past-projects">past projects</a> of Innovate to Grow since 2012, '
                        'and <a href="/current-projects">current student teams and projects</a> in this semester Innovate '
                        "to Grow classes and event.</li>"
                        '<li>You may sign up to judge or attend the <a href="https://i2g.ucmerced.edu/event" target="_blank" '
                        'rel="noopener noreferrer">next Innovate to Grow event</a>.</li>'
                        "</ul>"
                        '<p class="about-text">'
                        "For any questions or comments, please send us an email to: "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a></p>'
                    ),
                },
            },
        ],
    },
    {
        "slug": "engineering-capstone",
        "route": "/engineering-capstone",
        "title": "Engineering Capstone",
        "page_css_class": "capstone-page",
        "blocks": [
            {
                "block_type": "image_text",
                "sort_order": 0,
                "admin_label": "Engineering capstone content",
                "data": {
                    "heading": "Engineering Capstone",
                    "image_url": "/assets/about/engineering_capstone.webp",
                    "image_alt": "Engineering Capstone",
                    "image_position": "right",
                    "body_html": (
                        '<p class="capstone-text">'
                        "Engineering Capstone (also formerly known as Innovation Design Clinic) "
                        "challenges UC Merced's engineering students to become entrepreneurs of their "
                        "knowledge, skills and research applications.</p>"
                        '<p class="capstone-text">'
                        "Partner organizations and/or corporations play a vital role by helping the "
                        "students gain real-world experience and skills that will carry them into "
                        "their future careers, while the partners also get solutions to their own "
                        "engineering needs.</p>"
                        '<p class="capstone-text">'
                        "Engineering Capstone provides UC Merced's graduating seniors opportunities to "
                        "learn and contribute in teams that include practicing engineers and other "
                        "professionals from partner and sponsoring organizations.</p>"
                        '<p class="capstone-text">'
                        "The Capstone teams focus on engineering design projects chosen based on their "
                        "potential for significant near-term effects on communities, organizations "
                        "and/or industries in the region. The commitment of the teams and partners, "
                        "combined with the richness and intensity of the Innovate to Grow competition, "
                        "greatly enhances the traditional capstone experience.</p>"
                        '<p class="capstone-text">'
                        "Through Capstone, classroom learning and students' research activity are "
                        "coordinated with real-world design projects developed with partner "
                        "organizations and industries to help share diverse approaches to designing "
                        "and building solutions that fulfill client-based objectives.</p>"
                        '<p class="capstone-text">'
                        "Industry partners contribute sponsorships to the program's operation, and "
                        "each project sponsor's involvement ranges from providing funds to the "
                        "Innovate to Grow program, to engaging students in industry experiences.</p>"
                        '<p class="capstone-text">'
                        "We seek opportunities for students with partner organizations and industries "
                        "to collaborate, discover solutions to common problems, create and streamline "
                        "networking, and increase both radical and incremental innovation.</p>"
                        '<p class="capstone-text">'
                        "As industries and organizations become increasingly knowledge-based, and as "
                        "products, processes and business systems become more complex, UC Merced "
                        "engineering students are becoming an essential part of the industry and are "
                        "contributing to regional economic, social and cultural growth.</p>"
                        '<p class="capstone-text">'
                        'You may search all <a href="/past-projects">past projects</a> of Innovate '
                        'to Grow since 2012, and <a href="/current-projects">current student teams '
                        "and projects</a>.</p>"
                        '<p class="capstone-text">'
                        'You may <a href="/project-submission">propose a project</a> that can be '
                        "evaluated for fit in Engineering Capstone, Software Capstone, or an "
                        "internship, or potentially collaborative research with Faculty at UC Merced.</p>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "software-capstone",
        "route": "/software-capstone",
        "title": "Software Engineering Capstone",
        "page_css_class": "capstone-page",
        "blocks": [
            {
                "block_type": "image_text",
                "sort_order": 0,
                "admin_label": "Software capstone content",
                "data": {
                    "heading": "Software Engineering Capstone",
                    "image_url": "/assets/about/software_engineering_capstone.webp",
                    "image_alt": "Software Engineering Capstone",
                    "image_position": "right",
                    "body_html": (
                        '<p class="capstone-text">'
                        "Software Engineering Capstone (formerly known as Mobile App Challenge) "
                        "encourages UC Merced students to develop innovative software applications for "
                        "today's industry and societal needs, and currently involves students in the "
                        "Software Engineering CSE 120 class.</p>"
                        '<p class="capstone-text">'
                        "Partner organizations and companies provide problems and software projects, "
                        "and play a vital role by helping the students gain real-world experience and "
                        "skills that will carry them into their future careers, while the partners "
                        "also get solutions to their own software and data management needs.</p>"
                        '<p class="capstone-text">'
                        "The Software Capstone provides UC Merced's Computer Science seniors "
                        "opportunities to learn and contribute in teams that include practicing "
                        "professionals from partner and sponsoring organizations.</p>"
                        '<p class="capstone-text">'
                        "The Software teams focus on design and development projects chosen based on "
                        "their potential for significant near-term effects on communities, "
                        "organizations and/or industries in the region. The commitment of the teams "
                        "and partners, combined with the richness and intensity of the Innovate to "
                        "Grow competition, greatly enhances the software engineering experience.</p>"
                        '<p class="capstone-text">'
                        "Industry partners contribute sponsorships to the program's operation, and "
                        "each project sponsor's involvement ranges from providing funds to the "
                        "Innovate to Grow program, to engaging students in industry experiences.</p>"
                        '<p class="capstone-text">'
                        "We seek opportunities for students with partner organizations and industries "
                        "to collaborate, discover solutions to common problems, create and streamline "
                        "networking, and increase both radical and incremental innovation.</p>"
                        '<p class="capstone-text">'
                        "As industries and organizations become increasingly knowledge-based, and as "
                        "products, processes and business systems become more complex, UC Merced "
                        "computer science and engineering students are becoming an essential part of "
                        "the industry and are contributing to regional economic, social and cultural "
                        "growth.</p>"
                        '<p class="capstone-text">'
                        'You may search all <a href="/past-projects">past projects</a> of Innovate '
                        'to Grow since 2012, and <a href="/current-projects">current student teams '
                        "and projects</a>.</p>"
                        '<p class="capstone-text">'
                        'You may <a href="/project-submission">propose a project</a> that can be '
                        "evaluated for fit in Engineering Capstone, Software Capstone, or an "
                        "internship, or potentially collaborative research with Faculty at UC Merced.</p>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "about-engsl",
        "route": "/about-engsl",
        "title": "About Engineering Service Learning",
        "page_css_class": "engsl-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "EngSL content",
                "data": {
                    "heading": "About Engineering Service Learning",
                    "heading_level": 1,
                    "body_html": (
                        '<h2 class="engsl-section-title">'
                        '<a href="http://engineeringservicelearning.ucmerced.edu/" target="_blank" '
                        'rel="noopener noreferrer">Engineering Service Learning</a></h2>'
                        '<p class="engsl-text">'
                        "This UC Merced's cornerstone engineering experience, designed to expose "
                        "first-year students to the power of engineering. Through continuing "
                        "partnerships with local nonprofits, students design meaningful solutions to "
                        "the challenges their partners face.</p>"
                        '<p class="engsl-text">Unique opportunities include:</p>'
                        '<ul class="engsl-list">'
                        "<li>Participation by students from all majors and grade levels</li>"
                        "<li>Spans the course of a student's undergraduate career</li>"
                        "<li>Developing ties to their communities through relationships with local nonprofits</li>"
                        "</ul>"
                        '<p class="engsl-text">'
                        "We expect more than 300 people this year from industry, the community and "
                        "K-12 schools, plus our UC Merced students and faculty and staff members.</p>"
                        '<h3 class="engsl-subsection-title">How to Register?</h3>'
                        '<p class="engsl-text">'
                        "First, register for the lecture and then register for the corresponding lab, "
                        "which would be your team you are placed within. The lab is more important "
                        "than the lecture. Review the different "
                        '<a href="http://engineeringservicelearning.ucmerced.edu/teams-0" target="_blank" '
                        'rel="noopener noreferrer">research teams</a>.</p>'
                        '<p class="engsl-text">'
                        "The CRN for the lecture is 30459 (lower division), or 30463 (upper division).</p>"
                        '<p class="engsl-text">'
                        "The class starts as a 1 unit class but if you wish to have a leadership role "
                        "then it turns into 2 units. Review the "
                        '<a href="http://engineeringservicelearning.ucmerced.edu/teams/team-structure" '
                        'target="_blank" rel="noopener noreferrer">process</a>.</p>'
                        '<p class="engsl-text">'
                        "Schedule conflicts for the lecture only can be accommodated. Please send "
                        "lecture override requests to "
                        '<a href="mailto:esl@ucmerced.edu">esl@ucmerced.edu</a> with the following information:</p>'
                        '<ul class="engsl-list">'
                        "<li>Name</li>"
                        "<li>Student Id</li>"
                        "<li>ENGR 097 (lower division) or ENGR 197 (upper division)</li>"
                        "</ul>"
                        '<p class="engsl-text">'
                        "For current Teams &amp; Student Projects, visit "
                        '<a href="/projects-teams">Teams &amp; Projects</a>.</p>'
                    ),
                },
            },
        ],
    },
    {
        "slug": "sponsorship",
        "route": "/sponsorship",
        "title": "Sponsorship Opportunities",
        "page_css_class": "sponsorship-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Sponsorship content",
                "data": {
                    "heading": "Sponsorship Opportunities",
                    "heading_level": 1,
                    "body_html": (
                        '<h2 class="sponsorship-section-title">Why sponsor Innovate to Grow and the School of Engineering?</h2>'
                        '<p class="sponsorship-text">'
                        "The School of Engineering provides an intellectual environment for research "
                        "and education that makes UC Merced a magnet for innovation. Together, "
                        "students create transformational impacts on the world we live in.</p>"
                        '<p class="sponsorship-text">'
                        "Your donation improves the School of Engineering experiential learning "
                        "classes and their projects, and the bi-annual Innovate to Grow event and "
                        "student showcase. Gifts to the School of Engineering also help support "
                        "critical areas that ensure a strong foundation for building excellence in "
                        "our education programs, cross-functional research, and outstanding "
                        "partnerships and service. Our goal is to have enough award funding to help "
                        "the very best students accelerate toward a successful career and bright future.</p>"
                        '<h2 class="sponsorship-section-title">Recognition</h2>'
                        '<p class="sponsorship-text">'
                        "UC Merced is honored to acknowledge sponsors for their commitment to and "
                        "partnership with our programs. Recognition can include acknowledgment in "
                        "publicity materials, flyers and posters, email announcements, web pages, "
                        "media releases and publications of Innovate to Grow.</p>"
                        '<h2 class="sponsorship-section-title">How to Support</h2>'
                        '<p class="sponsorship-text">'
                        "If you would like to contribute as a sponsor of an Innovate to Grow project, "
                        "or as an affiliate to the Innovate to Grow event, please contact us at "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.</p>'
                        '<p class="sponsorship-text">'
                        'General <a href="https://securelb.imodules.com/s/1650/index.aspx?sid=1650&amp;gid=1&amp;pgid=474&amp;dids=12&amp;bledit=1&amp;appealcode=2014-15%20I2G" '
                        'target="_blank" rel="noopener noreferrer">Gifts</a> to the school also help '
                        "support critical areas that ensure a strong foundation for building excellence "
                        "in our education programs, cross-functional research, and outstanding "
                        "partnerships and service. Our goal is to have enough award funding to help "
                        "the very best students accelerate toward a successful career and bright future.</p>"
                        '<h2 class="sponsorship-section-title">Past Sponsors</h2>'
                        '<p class="sponsorship-text"><a href="/acknowledgement">2020 Sponsors</a></p>'
                        '<p class="sponsorship-text"><a href="/acknowledgement">2019 Sponsors</a></p>'
                        '<p class="sponsorship-text">'
                        '<a href="https://issuu.com/ucmsoe/docs/uc_merced_-_program_innovate_to_gro/14" '
                        'target="_blank" rel="noopener noreferrer">2018 Sponsors</a></p>'
                        '<p class="sponsorship-text">'
                        '<a href="https://issuu.com/ucmsoe/docs/innovate2growprogram_2017_final/17" '
                        'target="_blank" rel="noopener noreferrer">2017 Sponsors</a></p>'
                        '<p class="sponsorship-text">'
                        '<a href="https://ucmerced.box.com/v/innovatetogrow-sponsors-2016" '
                        'target="_blank" rel="noopener noreferrer">2016 Sponsors</a></p>'
                        '<p class="sponsorship-text"><a href="/sponsors/2015">2015 Sponsors</a></p>'
                        '<p class="sponsorship-text"><a href="/sponsors/2014">2014 Sponsors</a></p>'
                        '<p class="sponsorship-text">'
                        "For further information or if you have any questions, please contact us at "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.</p>'
                    ),
                },
            },
        ],
    },
    {
        "slug": "faqs",
        "route": "/faqs",
        "title": "Frequently Asked Questions",
        "page_css_class": "faq-page",
        "blocks": [
            {
                "block_type": "faq_list",
                "sort_order": 0,
                "admin_label": "FAQ items",
                "data": {
                    "heading": "Frequently Asked Questions",
                    "items": [
                        {
                            "question": "What is a Capstone Project?",
                            "answer_html": (
                                '<p class="faq-text"><strong>Engineering Capstone</strong> (formerly known as Innovation Design Clinic) is a senior-year, year-long design experience for engineering majors. See more at <a href="/engineering-capstone">Engineering Capstone</a>.</p>'
                                '<p class="faq-text"><strong>Software Capstone</strong> (formerly known as Mobile App Challenge) is a semester-long software engineering project course for computer science students. See more at <a href="/software-capstone">Software Capstone</a>.</p>'
                                '<p class="faq-text">A &quot;Capstone&quot; is a culminating academic experience in which students apply the knowledge and skills they have acquired throughout their coursework to a real-world project. The School of Engineering at UC Merced encompasses the following disciplines: Bioengineering, Civil &amp; Environmental Engineering, Computer Science &amp; Engineering, Materials Science &amp; Engineering, and Mechanical Engineering.</p>'
                            ),
                        },
                        {
                            "question": "What is Innovate to Grow?",
                            "answer_html": '<p class="faq-text">Innovate to Grow (I2G) is a unique &quot;experiential learning&quot; program at the UC Merced School of Engineering. It engages external partner organizations with teams of students who design systems to solve complex, real-world problems. At the end of each semester, the work completed by the student teams culminates in the Innovate to Grow event, which features student-led research presentations and highlights their project outcomes.</p>',
                        },
                        {
                            "question": "How are the Capstone projects proposed?",
                            "answer_html": (
                                '<p class="faq-text">A proposal is submitted with the following format:</p>'
                                '<ul class="faq-list"><li><strong>Organization:</strong> Name of the sponsoring organization</li><li><strong>Mentor(s):</strong> Name and contact information of the project mentor(s)</li><li><strong>Project Title:</strong> A descriptive title for the project</li><li><strong>Background:</strong> Context and background information</li><li><strong>Problem:</strong> The problem or challenge to be addressed</li><li><strong>Objective:</strong> The desired outcome or deliverable</li></ul>'
                                '<p class="faq-text">You may <a href="/project-submission">propose a project</a>, view <a href="/sample-proposals">sample proposals</a>, or search <a href="/past-projects">past projects</a>.</p>'
                            ),
                        },
                        {
                            "question": "What type of projects are applicable to Capstone?",
                            "answer_html": '<p class="faq-text"><strong>Engineering Capstone</strong> projects need to involve a significant design and prototyping component. These projects span two semesters (a full academic year).</p><p class="faq-text"><strong>Software Capstone</strong> projects need to involve a significant software engineering component. These projects are completed within one semester.</p>',
                        },
                        {
                            "question": "When is the deadline to submit project proposals?",
                            "answer_html": '<p class="faq-text">The deadline for projects starting in the <strong>Spring</strong> semester is <strong>December 31</strong>. The deadline for projects starting in the <strong>Fall</strong> semester is <strong>July 31</strong>.</p>',
                        },
                        {
                            "question": "How are the teams and projects selected?",
                            "answer_html": '<p class="faq-text">Faculty compiles the list of available projects and presents them to students. Students then select their preferred projects through a web-based poll. Teams are formed based on student preferences and project requirements.</p>',
                        },
                        {
                            "question": "How many projects can an organization submit?",
                            "answer_html": '<p class="faq-text">There is no hard limit on the number of projects an organization can submit. We welcome multiple proposals and will evaluate each for fit within the program.</p>',
                        },
                        {
                            "question": "Is there a time commitment for the sponsoring organization?",
                            "answer_html": '<p class="faq-text">Yes. Each project requires at least one designated mentor from the sponsoring organization. Mentors are expected to interact with their student team on a weekly or bi-weekly basis to provide guidance, feedback, and domain expertise.</p>',
                        },
                        {
                            "question": "Is there a financial commitment for the sponsoring organization?",
                            "answer_html": '<p class="faq-text">Financial sponsorship is not mandatory. However, donations are welcome and help support the program, student travel, prototyping materials, and the Innovate to Grow event. If you are interested in sponsoring, please visit our <a href="/partnership">partnership page</a>.</p>',
                        },
                        {
                            "question": "What is the timeline?",
                            "answer_html": (
                                '<p class="faq-text"><strong>Engineering Capstone</strong> has two cycles of year-long projects:</p>'
                                '<ul class="faq-list"><li><strong>CAP-1xx (Fall + Spring):</strong> Projects begin in August and conclude in May of the following year.</li><li><strong>CAP-2xx (Spring + Fall):</strong> Projects begin in January and conclude in December of the same year.</li></ul>'
                                '<p class="faq-text"><strong>Software Capstone</strong> has two cycles of semester-long projects:</p>'
                                '<ul class="faq-list"><li><strong>CSE-3xx (Fall):</strong> Projects run from August to December.</li><li><strong>CSE-3xx (Spring):</strong> Projects run from January to May.</li></ul>'
                            ),
                        },
                        {
                            "question": "What are the roles and expectations of judging at I2G?",
                            "answer_html": (
                                '<p class="faq-text">Judges at Innovate to Grow events are expected to:</p>'
                                '<ul class="faq-list"><li>Review student project presentations and posters</li><li>Evaluate the technical merit, creativity, and feasibility of each project</li><li>Provide constructive feedback to student teams</li><li>Score projects based on the provided rubric</li><li>Participate in deliberation to select award recipients</li></ul>'
                            ),
                        },
                        {
                            "question": "How is Capstone related to Innovate to Grow?",
                            "answer_html": '<p class="faq-text">Engineering Capstone and Software Capstone are academic classes offered by the School of Engineering at UC Merced. Innovate to Grow is the broader program and bi-annual showcase event where student teams present the results of their capstone projects, alongside other experiential learning classes. In short, the Capstone classes are the academic coursework, while Innovate to Grow is the program and event that highlights and celebrates student work.</p>',
                        },
                    ],
                },
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Seed CMS pages for Batch A (simple) and Batch B (rich content)."

    def add_arguments(self, parser):
        parser.add_argument("--page", type=str, help="Seed a specific page by slug.")
        parser.add_argument("--force", action="store_true", help="Overwrite existing pages.")

    def handle(self, *args, **options):
        target_slug = options.get("page")
        force = options.get("force", False)

        pages_to_seed = SEED_PAGES
        if target_slug:
            pages_to_seed = [p for p in SEED_PAGES if p["slug"] == target_slug]
            if not pages_to_seed:
                self.stderr.write(f"No seed data found for slug '{target_slug}'.")
                return

        for page_data in pages_to_seed:
            slug = page_data["slug"]
            existing = CMSPage.objects.filter(slug=slug).first()

            if existing and not force:
                self.stdout.write(f"  Skipping '{slug}' — already exists. Use --force to overwrite.")
                continue

            if existing and force:
                existing.hard_delete()
                self.stdout.write(f"  Deleted existing '{slug}'.")

            page = CMSPage.objects.create(
                slug=page_data["slug"],
                route=page_data["route"],
                title=page_data["title"],
                page_css_class=page_data.get("page_css_class", ""),
                status="published",
            )

            for block_data in page_data.get("blocks", []):
                CMSBlock.objects.create(
                    page=page,
                    block_type=block_data["block_type"],
                    sort_order=block_data["sort_order"],
                    admin_label=block_data.get("admin_label", ""),
                    data=block_data["data"],
                )

            block_count = len(page_data["blocks"])
            self.stdout.write(self.style.SUCCESS(f"  Created '{slug}' with {block_count} block(s)."))

        self.stdout.write(self.style.SUCCESS("Done."))
