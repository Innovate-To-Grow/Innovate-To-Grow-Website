"""Seed CMS pages for Batch C (judges, attendees, submission, proposals, event/video prep) and Batch D (legal, archive)."""

from django.core.management.base import BaseCommand

from cms.models import CMSBlock, CMSPage

SEED_PAGES = [
    # ==================== BATCH C ====================
    {
        "slug": "judges",
        "route": "/judges",
        "title": "Judge",
        "page_css_class": "judges-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Judges info",
                "data": {
                    "heading": "Judge",
                    "heading_level": 1,
                    "body_html": (
                        '<h2 class="judges-section-header">Judge Role</h2>'
                        '<ul class="judges-page-list">'
                        "<li>No formal preparation is needed to be a judge.</li>"
                        "<li>An engineering degree is not required.</li>"
                        "<li>You contribute based on your experience and professional judgment.</li>"
                        "<li>Judges fill out a questionnaire to evaluate each team.</li>"
                        "<li>The questionnaire will be provided via email, QR code, and Zoom chat.</li>"
                        "</ul>"
                        '<h2 class="judges-section-header">How to Sign Up for Judging</h2>'
                        '<p class="judges-page-text">'
                        "To indicate interest in judging, check the box while registering. Select "
                        "&quot;Yes&quot; in &quot;Interested in Judging?&quot; and you will be contacted "
                        "by the I2G Team."
                        "</p>"
                        '<p class="judges-page-text">'
                        "You can also express interest by emailing "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.'
                        "</p>"
                        '<h2 class="judges-section-header">Judging Preparation</h2>'
                        '<p class="judges-page-text">Review the following links to prepare:</p>'
                        '<ul class="judges-page-list">'
                        "<li>"
                        '<a href="https://youtu.be/aIQP17Vpbz4" target="_blank" rel="noopener noreferrer">'
                        "Video Instructions for I2G Judges</a></li>"
                        '<li><a href="/judging">Judging Forms</a></li>'
                        '<li><a href="/event">Event Info and Schedule</a></li>'
                        '<li><a href="/projects-teams">Projects &amp; Teams</a></li>'
                        "</ul>"
                        '<h2 class="judges-section-header">Event Day | Instructions for Judges</h2>'
                        '<h3 class="judges-page-subtitle">IN PERSON</h3>'
                        '<ul class="judges-page-list">'
                        "<li>Judges are encouraged to join the Expo.</li>"
                        '<li>Check the <a href="/schedule">schedule</a> for your assigned Room.</li>'
                        "<li>Go to the room 10 minutes before your scheduled time.</li>"
                        "<li>You are invited to the Award Ceremony.</li>"
                        "</ul>"
                        '<h3 class="judges-page-subtitle">ONLINE</h3>'
                        '<ul class="judges-page-list">'
                        '<li>Check the <a href="/schedule">schedule</a> for your assigned Zoom link.</li>'
                        "<li>Go to the room 10 minutes before your scheduled time.</li>"
                        '<li>Use the correct <a href="/judging">Judging form</a> for your track.</li>'
                        "<li>Enter by clicking the link of your assigned track.</li>"
                        "</ul>"
                        '<p class="judges-page-text">'
                        'For questions, email <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.'
                        "</p>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "attendees",
        "route": "/attendees",
        "title": "Attendees - How to Explore and Engage",
        "page_css_class": "attendees-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Attendees info",
                "data": {
                    "heading": "Attendees - How to Explore and Engage",
                    "heading_level": 1,
                    "body_html": (
                        '<p class="attendees-page-text">'
                        '<strong>WHEN</strong>: See the <a href="/schedule">schedule of the next event - semester</a>.'
                        "</p>"
                        '<h2 class="attendees-page-section-title">IN PERSON Attendees</h2>'
                        '<p class="attendees-page-text">'
                        "Register ASAP so badges can be prepared for you."
                        "</p>"
                        '<ul class="attendees-page-list">'
                        "<li>Park in the reserved area.</li>"
                        "<li>Walk or take the shuttle to the Expo.</li>"
                        "<li>Pick up your badge at Registration.</li>"
                        "<li>Coffee is available 30 minutes before the event starts.</li>"
                        "<li>Expo doors open on schedule.</li>"
                        "<li>Lunch will be provided in boxes.</li>"
                        "<li>Presentations start promptly.</li>"
                        "<li>Search the room of your desired track.</li>"
                        "<li>Award Ceremony at the end of the event.</li>"
                        "</ul>"
                        '<h2 class="attendees-page-section-title">ZOOM Attendees</h2>'
                        '<p class="attendees-page-text">'
                        "No Zoom info is needed prior to the event. Access to Zoom Tracks will be "
                        "activated on the I2G home page before the event begins."
                        "</p>"
                        '<h2 class="attendees-page-section-title">Online Features</h2>'
                        '<ul class="attendees-page-list">'
                        "<li>Zoom Rooms with consecutive team time slots.</li>"
                        "<li>Each team has a presentation followed by Q&amp;A.</li>"
                        "<li>Judges evaluate each team.</li>"
                        "</ul>"
                        '<h2 class="attendees-page-section-title">Important Notes on Zoom</h2>'
                        '<ul class="attendees-page-list">'
                        "<li>You need an authenticated Zoom account. "
                        '<a href="https://zoom.us/freesignup/" target="_blank" rel="noopener noreferrer">'
                        "Sign up for free here</a>.</li>"
                        "<li>Plan to be at the homepage 10 minutes before the event.</li>"
                        "<li>Zoom links will be available before the start of the event.</li>"
                        "</ul>"
                        '<h2 class="attendees-page-section-title">2 Ways to Participate</h2>'
                        '<h3 class="attendees-page-subtitle">#1 INTERACT (Judge)</h3>'
                        '<ul class="attendees-page-list">'
                        '<li><a href="/event">Register</a> for the event.</li>'
                        "<li>Select &quot;Yes&quot; for judging when registering.</li>"
                        "<li>You will be contacted for your assigned Track.</li>"
                        "<li>Sign in to Zoom on the day of the event.</li>"
                        '<li>See <a href="/judges">instructions for Judges</a>.</li>'
                        "</ul>"
                        '<h3 class="attendees-page-subtitle">#2 ATTEND</h3>'
                        '<ul class="attendees-page-list">'
                        '<li><a href="/event">Register</a> for the event.</li>'
                        "<li>Select &quot;No&quot; for judging when registering.</li>"
                        '<li>Join from the <a href="/schedule">schedule</a> on the day of the event.</li>'
                        "</ul>"
                        '<h2 class="attendees-page-section-title">Summary</h2>'
                        '<ul class="attendees-page-list">'
                        "<li>Register for the event.</li>"
                        "<li>Stay tuned for updates.</li>"
                        "<li>Prepare your Zoom account.</li>"
                        '<li>Questions? Email <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.</li>'
                        "</ul>"
                        '<p class="attendees-page-text attendees-page-closing">'
                        "Thank you for participating and ... see you soon!"
                        "</p>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "project-submission",
        "route": "/project-submission",
        "title": "Project Submission",
        "page_css_class": "submission-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Project submission info",
                "data": {
                    "heading": "Project Submission",
                    "heading_level": 1,
                    "body_html": (
                        '<section class="submission-section">'
                        '<h2 class="submission-section-title">Submit a Project</h2>'
                        '<a href="https://forms.gle/ihQG5ieEvCKfYP5n9" target="_blank" '
                        'rel="noopener noreferrer" class="submission-button">'
                        "Click Here to Submit Your Project</a>"
                        "</section>"
                        '<section class="submission-section">'
                        '<h2 class="submission-section-title">What is &quot;Capstone&quot; Project?</h2>'
                        '<p class="submission-text">'
                        "The Innovate to Grow (I2G) program provides senior and graduating engineering "
                        "students with the opportunity to work on their Engineering Capstone and Software "
                        "Engineering class through addressing a real world problem posed by an external "
                        "organization. I2G is currently a semester-long program, and a project is assigned "
                        "to a team of 3-5 students with majors/skills that match the project requirements. "
                        "I2G provides the opportunity to sponsor organizations to perform studies, "
                        "conjecture solutions to problems, test ideas, and assess students on real work. "
                        "The School of Engineering has the following five Departments and Engineering "
                        "Majors: Mechanical, Civil and Environmental, Chemical and Material Science, "
                        "Biological, and Computer Science."
                        "</p>"
                        "</section>"
                        '<section class="submission-section">'
                        '<h2 class="submission-section-title">How are teams and projects selected?</h2>'
                        '<p class="submission-text">'
                        "The list of project summaries proposed by partners, and applicable to Engineering "
                        "or Software Capstone, are presented by the Professors of the respective class for "
                        "the students to review and select in a web poll. Based on the results, the "
                        "Professor forms teams to optimize the student's preferences, the engineering "
                        "majors required for the project, and the priority of the proposed projects."
                        "</p>"
                        "</section>"
                        '<section class="submission-section">'
                        '<h2 class="submission-section-title">How is Capstone related to Innovate to Grow?</h2>'
                        '<p class="submission-text">'
                        "Innovate to Grow is the event in which we showcase our student's engineering "
                        "design talent from the Capstone projects. The Final Design Review is embedded "
                        "in the event program, which culminates in a multi-faceted competition that also "
                        "encompasses the School of Engineering's signature programs: Engineering Capstone, "
                        "Software Engineering Capstone, and Engineering Service Learning."
                        "</p>"
                        "</section>"
                        '<section class="submission-section">'
                        '<h2 class="submission-section-title">'
                        "Can I see examples of Capstone projects and proposals?"
                        "</h2>"
                        '<p class="submission-text">'
                        "If you would like to see projects to get ideas for your submission you may:"
                        "</p>"
                        '<ul class="submission-list">'
                        "<li>Search the database of final summaries of "
                        '<a href="/past-projects">past projects</a> of Innovate to Grow since 2012.</li>'
                        "<li>View "
                        '<a href="/sample-proposals">samples of project proposals</a> submitted by other '
                        "organizations, including Engineering and Software problems.</li>"
                        "</ul>"
                        "</section>"
                        '<section class="submission-section">'
                        '<h2 class="submission-section-title">'
                        "What are the agreements for a Capstone - I2G project?"
                        "</h2>"
                        '<p class="submission-text">'
                        "You may find more information about execution of projects, agreements, and "
                        "timelines at:"
                        "</p>"
                        '<ul class="submission-list">'
                        "<li>Template of the "
                        '<a href="https://i2g.ucmerced.edu/I2G-student-agreement" target="_blank" '
                        'rel="noopener noreferrer">Student Agreement</a>.</li>'
                        "<li>Template of the "
                        '<a href="https://i2g.ucmerced.edu/I2G-project-sponsor-acknowledgement" '
                        'target="_blank" rel="noopener noreferrer">Partner Agreement</a>.</li>'
                        "<li>Template of the "
                        '<a href="https://i2g.ucmerced.edu/template-email-team-students" target="_blank" '
                        'rel="noopener noreferrer">Project - Team with signed agreements</a>.</li>'
                        "</ul>"
                        "</section>"
                        '<section class="submission-section">'
                        '<h2 class="submission-section-title">Where can I find more information?</h2>'
                        '<p class="submission-text">'
                        "You may find more information about execution of projects, agreements, and "
                        "timelines at: "
                        '<a href="https://i2g.ucmerced.edu/FAQs" target="_blank" rel="noopener noreferrer">'
                        "Frequently Asked Questions (FAQs)</a>"
                        "</p>"
                        "</section>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "sample-proposals",
        "route": "/sample-proposals",
        "title": "Sample Project Proposals",
        "page_css_class": "proposals-page",
        "blocks": [
            {
                "block_type": "proposal_cards",
                "sort_order": 0,
                "admin_label": "Sample proposals",
                "data": {
                    "heading": "Sample Project Proposals",
                    "proposals": [
                        {
                            "type": "Engineering Capstone",
                            "title": "Automated Production Line Optimization",
                            "organization": "Sweep",
                            "background": (
                                "Sweep is an IoT Internet of things company that harnesses big data and "
                                "machine learning to improve operational efficiency in industry. We rely on "
                                "collecting valuable industrial equipment data through non-invasive sensors "
                                "technologies to service our industrial/commercial customers. Product "
                                "development of sensor technologies fuels our growth and innovation is "
                                "crucial to reducing costs and improving capability."
                            ),
                            "problem": (
                                "Machine Centers of our production process require that product be moved "
                                "manually between machine centers. This increases the time it takes to "
                                "produce product and increases the risk for defects due to manual handling "
                                "of product."
                            ),
                            "objectives": (
                                "Optimize a manufacturing production line for small to medium runs of "
                                "electrical and mechanical manufacturing components. Analyze and provide "
                                "recommendations for most efficiently timed process from circuit board "
                                "placement, testing, assembly and logistics. Build, manufacture and test, "
                                "automation components to limit user interaction. Automate production of "
                                "mechanical injection molded components, pcb assemblies and final product "
                                "assembly."
                            ),
                        },
                        {
                            "type": "Software Capstone",
                            "title": "Business Process Applications for a Public Agency",
                            "organization": "BART",
                            "background": (
                                "The client is the SF Bay Area Rapid Transit (BART). They are in the "
                                "business of moving people in electrified rail cars, across a collective "
                                "122 miles of rail tracks around and in the city of San Francisco. They are "
                                "a public transportation industry headquartered in Oakland, CA. BART is in "
                                "the midst of a capital improvement renewal effort to upgrade and replace "
                                "$3B or more in capital infrastructure. There is a need to provide the "
                                "highest level of professional project management, and to perform this work "
                                "most efficiently, and accurately."
                            ),
                            "problem": (
                                "We are looking to bring the latest business technologies to our processes. "
                                "Improving the efficiency of the project management process by implementing "
                                "single data base synching from our current databases. Our systems using "
                                "the maintenance database, Maximo, support the planning, scheduling, "
                                "recording, and data collection for entire capital and maintenance teams. "
                                "We need to gather real time data from these databases and collate the data "
                                "for notifications. By achieving real time notifications and linking data, "
                                "decisions, planning, and forecasting will be improved. We are flexible on "
                                "the type of data and how to integrate data and establishing automated "
                                "notifications."
                            ),
                            "objectives": (
                                "We have an opportunity for a student group to generate, collate, and "
                                "distribute data from our Maximo database. We would like an extraction, "
                                "population, and integration with the data, real time alerts, and business "
                                "processes that can provide real time data collection and event forecasting. "
                                "Final development is a user friendly data output that can be integrated "
                                "into capital project management reports, capturing real time maintenance "
                                "and capital work."
                            ),
                        },
                        {
                            "type": "Engineering Capstone",
                            "title": "Recovery of Starlite Technology",
                            "organization": "NASA Jet Propulsion Laboratory",
                            "background": (
                                "The NASA Jet Propulsion Laboratory (JPL) is a Federally Funded Research "
                                "and Development Center, located in the Arroyo Seco Mountains in Pasadena, "
                                "CA. Originating as a laboratory of the California Institute of Technology, "
                                "JPL has been in the aerospace industry since the 1920s. Dedicated to the "
                                "unmanned exploration of the solar system, JPL has built interplanetary "
                                "probes, orbiters, and landers to explore our universe and expand our "
                                "knowledge."
                            ),
                            "problem": (
                                "Applications of heat transfer are ubiquitous in spacecraft applications. "
                                "Examples are protecting the rocket engines from the hot exhaust used for "
                                "propulsion, keeping sensitive electronics on board thermally insulated "
                                "from the cold space, as well as protection from solar irradiation. In the "
                                "1970s, British hairdresser and amateur chemist Maurice Ward invented "
                                "Starlite \u2013 a material with fantastic thermal properties. He "
                                "demonstrated that a thin coating of this material could be charred with a "
                                "blowtorch, but the other side would be cold enough to safely touch it. "
                                "There was no description of how this material was made, and after Mr. "
                                "Wards death, there is no knowledge of producing the material. Efforts to "
                                "reinvent this material were made, but with minimal success."
                            ),
                            "objectives": (
                                "The recovery of Starlite would be a substantial advancement in space "
                                "technologies. But with the information available, this material is short "
                                "of 'unobtaininum', or an imaginary substance. The objective of this "
                                "project is to research the feasibility, attempt the fabrication, and "
                                "characterize this material. The material produced should have similar "
                                "properties, but shall also be properly investigated and understood, such "
                                "that future generations can produce it as well."
                            ),
                        },
                        {
                            "type": "Software Capstone",
                            "title": "Farm Operations Dashboard",
                            "organization": "Bowles Farming Co.",
                            "background": (
                                "Bowles Farming Company is a sixth generation family farm out of Los Banos "
                                "CA. Bowles continuously strives to implement new technology to improve "
                                "processes and activities around the farm."
                            ),
                            "problem": (
                                "Agworld is a modern farm management program that allows operations to "
                                "plan and track jobs and costs associated in one program. We will be using "
                                "agworld for task assignment and data collection. Agworld has a very robust "
                                "API which allows programs to extract as much information as needed about "
                                "jobs in the database. Although a large amount of data is logged in "
                                "agworld, it is not presented as well as it could be."
                            ),
                            "objectives": (
                                "A step toward making agworld data presentable is to have a dashboard "
                                "showing upcoming and completed jobs while highlighting overdue jobs. This "
                                "data would be presented on TVs or as web platforms for users around the "
                                "farm to get updated about what is going on and what has happened. This "
                                "communication tool will help get everyone on the same page about what "
                                "operations has done and what's coming up."
                            ),
                        },
                        {
                            "type": "Engineering Capstone",
                            "title": "Milkweed Harvester",
                            "organization": "Bowles Farming Co.",
                            "background": (
                                "Bowles Farming Company is a sixth generation family farm out of Los Banos, "
                                "CA. Bowles continuously strives to implement new technology to improve "
                                "processes and activities around the farm."
                            ),
                            "problem": (
                                "Milkweed is a native species in the California's Central Valley and is a "
                                "critical element in Monarch habitat, as it provides both forage for adult "
                                "butterflies and protection for developing larvae. With changes in "
                                "California land use pressures, milkweed populations have declined, "
                                "contributing to a correlating decline in monarch populations. Milkweed "
                                "seed is naturally distributed via pappus (like a dandelion) and when "
                                "collected, is a mixture of floss and seed. Today, most milkweed is "
                                "collected by hand, which is a costly and inefficient process. New methods "
                                "need to be developed for both harvesting and cleaning milkweed seeds in "
                                "order to efficiently meet the habitat demands of the species."
                            ),
                            "objectives": (
                                "Milkweed harvesting is the most intensive effort in the production. "
                                "Milkweed seed is most often collected by hand, and occasionally, via "
                                "combine. There are significant disadvantages to both. Hand collection of "
                                "milkweed seed is cost-prohibitive when considering the environmental "
                                "demands, and combining seed results in the collection of immature "
                                "materials and can damage the milkweed plants. A successful solution "
                                "should (1) be mechanized, (2) minimize damage to milkweed plants, and "
                                "(3) be scalable."
                            ),
                        },
                    ],
                    "footer_html": (
                        "<p>Expectations and Submission: please review the "
                        '<a href="https://docs.google.com/document/d/1HhZ8r7FP9kPeJTSrvy4nBc0A6jBArSd19Y9O9g1xgUc/edit" '
                        'target="_blank" rel="noopener noreferrer">'
                        "expectations and terms of the I2G Program</a> "
                        "for your organization's participation, and "
                        '<a href="https://ucmerced.az1.qualtrics.com/jfe/form/SV_4OA7I03KTLgQcGF?" '
                        'target="_blank" rel="noopener noreferrer">'
                        "submit the project with the form</a> "
                        "or email this filled document to: "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a></p>'
                    ),
                },
            },
        ],
    },
    {
        "slug": "event-preparation",
        "route": "/event-preparation",
        "title": "Students & Teams - I2G Event Preparation",
        "page_css_class": "student-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Event preparation guide",
                "data": {
                    "heading": "Students & Teams - I2G Event Preparation",
                    "heading_level": 1,
                    "body_html": (
                        # Section 1: Intro to I2G
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Intro to I2G - Program and Event</h2>'
                        '<p class="student-text">'
                        "Innovate to Grow (I2G) is a unique &quot;experiential learning&quot; program that "
                        "engages external partner organizations with teams of students who design systems "
                        "to solve complex, real-world problems."
                        "</p>"
                        '<p class="student-text">'
                        "At the end of each semester, the work completed by the student teams culminates "
                        "in the Innovate to Grow event. Teams are assigned to tracks, where they present "
                        "their projects to judges and public attendees, followed by Q&amp;A. Judges will "
                        "then select the track winners, which will be announced on the web site (or an "
                        "award ceremony)."
                        "</p>"
                        '<p class="student-text">'
                        "Notice that the I2G showcase is a great opportunity for students to communicate "
                        "their projects and experience to the public, to participate in an engineering "
                        "challenge, to engage with professionals, and to find internships and job "
                        "opportunities. You may see more information "
                        '<a href="/about">about I2G</a>.'
                        "</p>"
                        "</section>"
                        # Section 2: Event Preparation
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Event Preparation</h2>'
                        '<p class="student-text">'
                        "Innovate to Grow (I2G) is currently executed in multiple Zoom rooms (tracks). "
                        "Here students and teams may find important info to prepare for the event."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>Zoom info</strong>: The zoom rooms (links) will be activated on the I2G "
                        "home page a few minutes before the event starts. You do not need the zoom links "
                        "in advance."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>No Registration needed</strong>: Students that are part of a class in "
                        "the current semester I2G event are <strong>automatically registered</strong>. "
                        "Students <strong>MUST NOT register for I2G in Eventbrite</strong>: this would "
                        "complicate sorting through registrations to manage judges and attendees!"
                        "</p>"
                        '<p class="student-text">'
                        "In summary: all students need to do on the day of the event is to go to the I2G "
                        "home page."
                        "</p>"
                        "</section>"
                        # Section 3: Team Name
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Team Name</h2>'
                        '<p class="student-text">'
                        "Unique and creative Team Names were started by students early on in Innovate to "
                        "Grow, and has since become a tradition. If a team does not want to invent a "
                        "unique name, it helps to have a short name for the project."
                        "</p>"
                        '<p class="student-text">Guidelines for the &quot;Team Name&quot;:</p>'
                        '<ul class="student-list">'
                        "<li>Can be creative, but...</li>"
                        "<li>Must not be offensive or inappropriate</li>"
                        "<li>Maximum 36 characters</li>"
                        "<li>Will be reviewed and approved</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "You may view all team names and project abstracts since 2012 in the "
                        '<a href="/past-projects">Past Projects</a>.'
                        "</p>"
                        "</section>"
                        # Section 4: Abstract
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Abstract</h2>'
                        '<p class="student-text">'
                        "The abstract is a short summary of the background, the problem/objective, and "
                        "the solution/deliverable. Similarly to the abstract in a journal, or an "
                        "executive summary of a business plan or project, it is intended to quickly "
                        "summarize the goals and accomplishments."
                        "</p>"
                        '<p class="student-text">'
                        "The abstract of a Capstone / I2G project will be published and searchable in "
                        "the Innovate to Grow website, and likely the most read content of I2G teams. "
                        "Therefore, it should highlight excellence in engineering education, "
                        "professionality, and communication. It should be written clearly and concisely "
                        "for a general audience. Since it is for public release, it must not contain "
                        "confidential information. You may view all team names and project abstracts "
                        'since 2012 in the <a href="/past-projects">Past Projects</a>.'
                        "</p>"
                        '<p class="student-text">The best approach to write your Capstone abstract:</p>'
                        '<ol class="student-ordered-list">'
                        "<li>Review the original background, problem, objective of the project summary "
                        "as proposed by the client and shared at the beginning of the semester.</li>"
                        "<li>Condense the background, problem, objective.</li>"
                        "<li>Add the final result of what you did, or what you delivered.</li>"
                        "<li>Check spelling, punctuation, spaces, Caps, acronyms, ...</li>"
                        "<li>Review to make sure it is fluid, logical, precise, succinct, and correct "
                        "(client, users, etc.)</li>"
                        "<li>Ask feedback and approval by your client for public release.</li>"
                        "</ol>"
                        '<p class="student-text">Recommended abstract structure:</p>'
                        '<ul class="student-list">'
                        "<li>Client is/does ....</li>"
                        "<li>The problem is that ... or ... our project was to ...</li>"
                        "<li>We (or Our team) designED (PAST tense) something with such and such that "
                        "DOES this and that</li>"
                        "<li>The model/tool IS / SHALL BE used by ... or was tested by ... and SHALL "
                        "produce this benefit.</li>"
                        "</ul>"
                        '<p class="student-text">Abstract common problems:</p>'
                        '<ul class="student-list">'
                        "<li>Spelling errors, lowercases when should be Caps.</li>"
                        "<li>It sounds like a plan (our task is to ... or we will do) rather than "
                        "project result.</li>"
                        "<li>Confusion between the problem and the solution.</li>"
                        "<li>Unclear whether the technical description was the status quo or the result "
                        "of your work.</li>"
                        "<li>Rough sentences: without subject, or verb, wrong punctuation, repeated "
                        "words, etc.</li>"
                        "</ul>"
                        "</section>"
                        # Section 5: Slides
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Slides</h2>'
                        '<p class="student-text">'
                        "Please follow the additional guidelines provided to your class. These are "
                        "recommendations for ALL slides and presentations to provide context and "
                        "conclude with action."
                        "</p>"
                        '<h3 class="student-section-subtitle">First Slide</h3>'
                        '<ul class="student-list">'
                        "<li>Team name</li>"
                        "<li>Team number (e.g. CAP-123 or CSE-321)</li>"
                        "<li>Project title</li>"
                        "<li>Industry partner name - use a logo if possible</li>"
                        "<li>Optionally, indicate the client/mentor name(s), if they OKed</li>"
                        "</ul>"
                        '<h3 class="student-section-subtitle">Every Slide Footer</h3>'
                        '<p class="student-text">'
                        "Throughout the presentation, place a footer with:"
                        "</p>"
                        '<ul class="student-list">'
                        "<li>Team name</li>"
                        "<li>Team number</li>"
                        "<li>Project title</li>"
                        "<li>Industry partner name</li>"
                        "<li>Slide number</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "This will remind attendees and judges who you are even if they come in late "
                        "or forget."
                        "</p>"
                        '<h3 class="student-section-subtitle">Last Slide</h3>'
                        '<ul class="student-list">'
                        "<li>The same information as the first slide (may use smaller fonts or logos)</li>"
                        "<li>Team members' names with corresponding contact info (see contact info "
                        "guidelines)</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "Very importantly, during the presentation, remember to end and stay on this "
                        "last slide (no &quot;Questions?&quot; nor &quot;Thank you!&quot; slide after "
                        "that or the audience loses your info)."
                        "</p>"
                        "</section>"
                        # Section 6: Poster
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Poster</h2>'
                        '<p class="student-text">'
                        "The team's goal at an expo should be to stop people to engage them. In case "
                        "someone wants to read (less likely), then the content of the poster should be "
                        "clear and concise. Therefore, the most important part of the poster is to "
                        "identify:"
                        "</p>"
                        '<ul class="student-list">'
                        "<li>Team name</li>"
                        "<li>Team number (e.g. CAP-123 or CSE-321)</li>"
                        "<li>Project title</li>"
                        "<li>Industry partner name - use a logo if possible</li>"
                        "<li>Optionally, indicate the client/mentor name(s), if they OKed</li>"
                        "<li>The students with corresponding contact info (see contact info "
                        "guidelines)</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "This information should all be at the top (where people walking by look at "
                        "first, along with faces)."
                        "</p>"
                        "</section>"
                        # Section 7: Contact Info
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Contact Info</h2>'
                        '<p class="student-text">'
                        "These recommendations for how to present the team members' contact information "
                        "will facilitate the audience to recognize you, write your name/email, remember "
                        "you later:"
                        "</p>"
                        '<ul class="student-list">'
                        "<li>Contact information of a student placed under the corresponding name</li>"
                        "<li>Use a personal email (unless you will check or forward your school "
                        "email)</li>"
                        "<li>Make your contact info very easy to read (shorter text, larger font)</li>"
                        "<li>Do not write &quot;Personal Email:&quot; or even &quot;Email: ....&quot; "
                        "&mdash; everyone knows that a@b.c is an email</li>"
                        "<li>Do not write HTTPS://WWW. .... just linkedin.com/in/johndoe/ or "
                        "Linkedin: johndoe</li>"
                        "<li>Get a shorter LinkedIn handle rather than the default: "
                        "john-doe-6b21ba797f</li>"
                        "<li>Preferably, place the corresponding student photo near the contact "
                        "info.</li>"
                        "</ul>"
                        '<p class="student-text"><strong>Examples</strong>:</p>'
                        '<p class="student-text">'
                        "Firstname Lastname<br />"
                        "email@whatever.com<br />"
                        "linkedin.com/in/linkedin-name"
                        "</p>"
                        '<p class="student-text">'
                        "Stefano Foresti<br />"
                        "email@stefanoforesti.com<br />"
                        "linkedin.com/in/steforesti"
                        "</p>"
                        "</section>"
                        # Section 8: Video Preparation
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Video Preparation</h2>'
                        '<p class="student-text">'
                        "Please read the detailed "
                        '<a href="/video-preparation">instructions on how to prepare video '
                        "presentations</a> including:"
                        "</p>"
                        '<ul class="student-list">'
                        "<li>Content preparation</li>"
                        "<li>Presentation and slides structure</li>"
                        "<li>Video recording recommendations</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "Please consult with your class instructor for further details including:"
                        "</p>"
                        '<ul class="student-list">'
                        "<li>Deadlines for submission</li>"
                        "<li>Specific requirements in content preparation</li>"
                        "<li>Content and files upload instructions</li>"
                        "<li>Other requirements</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "Please notice that your video may be stitched and compiled in a video file "
                        "for a whole track, and that technical hosts will start-pause the video based "
                        "on the event schedule and the live Q&amp;A sessions. Therefore, please "
                        "consider these <strong>important additional requirements for video delivery "
                        "during an online event</strong>."
                        "</p>"
                        '<h3 class="student-section-subtitle">Video Start</h3>'
                        '<ul class="student-list">'
                        "<li>Start the video on mute on the first slide (Team #, Name, Project, "
                        "Client, Students).</li>"
                        "<li>Start speaking 5 seconds after starting the video on the first "
                        "slide.</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "This will allow smooth transitions between presentations and Q&amp;As, as "
                        "well as context for judges."
                        "</p>"
                        '<h3 class="student-section-subtitle">Video End</h3>'
                        '<ul class="student-list">'
                        "<li>Conclude your presentation on the slide with Team #, Name, Project, "
                        "Client, and the Students' contact info.</li>"
                        "<li>At the end of your presentation and closing statements, continue the "
                        "video recording on <strong>mute for 15 seconds on the last contact "
                        "slide</strong>.</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "This will facilitate the tech hosts pausing the video after you have "
                        "completed speaking, and keeping your last slide, which may persist during "
                        "the Q&amp;A session: therefore, the judges keep having the context to write "
                        "their forms, and attendees can note your info."
                        "</p>"
                        '<p class="student-text">Notice:</p>'
                        '<ul class="student-list">'
                        "<li>It is counterproductive to end the presentation on &quot;Thank you&quot; "
                        "or &quot;Questions?&quot; or &quot;End of Slides&quot;.</li>"
                        "<li>The time added to your video while muted during opening and closing "
                        "slides will not count towards the maximum video length (of your class), "
                        "because they may be cut in the stitching and video preparation process.</li>"
                        "</ul>"
                        "</section>"
                        # Section 9: Content Upload - File Naming
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Content Upload - File Naming</h2>'
                        '<p class="student-text">'
                        "I2G involves dozens of projects, partners, judges, and hundreds of students "
                        "each semester. Since the beginning in 2012 I2G involved several hundreds of "
                        "projects. All teams and abstracts can be searched in the "
                        '<a href="/past-projects">Past Projects</a> section of the web site. All '
                        "files related to projects videos, presentations, posters, reports are kept "
                        "confidential and archived to be findable."
                        "</p>"
                        '<p class="student-text">'
                        "We need your cooperation to ensure that the files are named so that they are "
                        "<strong>recognizable, sortable, and findable</strong>: this will further "
                        "strengthen the program and the opportunities for Students, Partners and UC "
                        "Merced."
                        "</p>"
                        '<p class="student-text">'
                        "When creating, sharing, and uploading files use this convention:"
                        "</p>"
                        '<p class="student-text">'
                        "<strong>YYYY-Semester-PROgramTeam##-assignment.filetype</strong>"
                        "</p>"
                        '<p class="student-text">Where:</p>'
                        '<ul class="student-list">'
                        "<li>YYYY = the year</li>"
                        "<li>Semester = 01-Spring and 08-Fall are the semester with a digit prior for "
                        "sortability</li>"
                        "<li>PROgram = CAP (Eng. Capstone) or CSE (Software Eng.)</li>"
                        "<li>Assignment = video, slides, poster, report, other ....</li>"
                        "<li>Filetype: depending on file</li>"
                        "</ul>"
                        '<p class="student-text">For instance:</p>'
                        '<ul class="student-list">'
                        "<li>2021-01-Spring-CAP03-video.mp4 &mdash; if ENGR 190 team 5 submits the "
                        "video</li>"
                        "<li>2022-08-Fall-CSE12-slides.ppt &mdash; if CSE120 team 12 submits the "
                        "slides</li>"
                        "</ul>"
                        "</section>"
                        # Section 10: Team Information - Schedule Review
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Team Information - Schedule Review</h2>'
                        '<p class="student-text">'
                        "Please review the schedule of the I2G event: please search in the navigation "
                        "bar the link to the current semester, and links to the semester program are "
                        "found there."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>For the current semester</strong>, check the schedule and "
                        '<a href="/current-projects">current projects and teams</a>.'
                        "</p>"
                        '<ol class="student-ordered-list">'
                        "<li>Find your team number in the schedule (CAPxxx, CSExxx, CEExxx or "
                        "EngSLxxx).</li>"
                        "<li>Check if your Client is correctly listed in the schedule.</li>"
                        "<li>Mouseover your team number and check if the popup shows your correct "
                        "&quot;Team Name - Project Title&quot;.</li>"
                        "<li>Click on your team number, which shall open a datatable with "
                        "team-project details. You may also find the details searching for your "
                        'team in <a href="/current-projects">Current Projects</a>.</li>'
                        "<li>Open your team details by clicking the icon/arrow, and check if they "
                        "are correct:"
                        '<ul class="student-list">'
                        "<li>Team Name</li>"
                        "<li>Project Title</li>"
                        "<li>Organization (client)</li>"
                        "<li>Abstract</li>"
                        "<li>Student Names</li>"
                        "</ul></li>"
                        "<li>Check if any team member has a schedule conflict during your team's "
                        "slot. Keep in mind that while the video is pre-recorded, the Q&amp;A "
                        "session is live, so the team needs to be prepared to excel at the Q&amp;A "
                        "session.</li>"
                        "</ol>"
                        '<p class="student-text">'
                        "If there is a <strong>schedule conflict</strong> or if you find "
                        "<strong>incorrect information</strong>, please "
                        "<strong>contact immediately</strong> your instructor and "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.'
                        "</p>"
                        "</section>"
                        # Section 11: The Event Day - I2G Q&A Session
                        '<section class="student-section">'
                        '<h2 class="student-section-title">The Event Day - I2G Q&amp;A Session</h2>'
                        '<p class="student-text">'
                        "<strong>Team's time slot</strong>. The track is divided in time slots, and "
                        "the zoom host will do the following in each team's slot:"
                        "</p>"
                        '<table class="student-table">'
                        "<thead><tr><th>Phase</th><th>Actions</th></tr></thead>"
                        "<tbody>"
                        "<tr>"
                        "<td>Transition from previous team presentation (+/- 2 min based on "
                        "schedule)</td>"
                        "<td><ul><li>Tech Host MUTES ALL participants</li></ul></td>"
                        "</tr>"
                        "<tr>"
                        "<td>Pre-recorded Video (10-20 minutes depending on class)</td>"
                        "<td><ul>"
                        "<li>The Tech Host will share the student video presentation</li>"
                        "<li>The Tech Host will unmute students before the end of the "
                        "presentation</li>"
                        "<li>The Tech Host will pause the video on the final slide (with the QR "
                        "Code for the judging survey)</li>"
                        "</ul></td>"
                        "</tr>"
                        "<tr>"
                        "<td>Live Q/A (8-12 minutes depending on class)</td>"
                        "<td><ul>"
                        "<li>The Tech Host will allow one student to share their screen with "
                        "reference materials (slide deck or simulation) during the Q/A</li>"
                        "<li>The Moderator will read questions to students from the chat</li>"
                        "<li>The Tech Host will resume the video with an intermission slide during "
                        "the transition</li>"
                        "<li>The Tech Host will remove screen sharing permissions from the "
                        "student</li>"
                        "</ul></td>"
                        "</tr>"
                        "<tr>"
                        "<td>Transition to next presentation</td>"
                        "<td><ul><li>The Tech Host WILL MUTE all participants</li></ul></td>"
                        "</tr>"
                        "</tbody>"
                        "</table>"
                        '<p class="student-text">'
                        "<strong>Presence</strong>."
                        "</p>"
                        '<ul class="student-list">'
                        "<li>Students are not required to be present during the whole event "
                        "(although, highly encouraged).</li>"
                        "<li>Teams MUST join the zoom room of your designated track at the start "
                        "of the event. If you cannot attend the whole event, please join your "
                        "designated track's zoom room no less than 10-15 minutes before the "
                        "scheduled start time of your video presentation.</li>"
                        "<li>The presentation will start about the time on the schedule (+ or - 2 "
                        "minutes).</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "<strong>Attire</strong>."
                        "</p>"
                        '<ul class="student-list">'
                        "<li>Dress business casual and have a professional presence.</li>"
                        "<li>Ideally, use the same "
                        '<a href="/video-preparation">preparation as in the video recording</a>.</li>'
                        "<li>Use a proper background, possibly the "
                        '<a href="https://ucmerced.box.com/s/rvd24ng4hyptg27rp5cposeo0b8ad6rl" '
                        'target="_blank" rel="noopener noreferrer">'
                        "I2G approved virtual background</a>.</li>"
                        "<li>Please make sure if you are using a zoom profile picture, it is "
                        "professional.</li>"
                        "<li>Audio: no background noise, test audio level.</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "<strong>Zoom</strong>."
                        "</p>"
                        '<ul class="student-list">'
                        "<li>Check the quality of the internet connection.</li>"
                        "<li>Sign in your Zoom account.</li>"
                        "<li>Click the Zoom Room # of your Track.</li>"
                        "<li>Make sure your &quot;Display Name&quot; is your Full Name.</li>"
                        "<li>Enter the Passcode.</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "The zoom tech host will know your names and make you co-host the designated "
                        "student to deliver Q&amp;A slides - if needed."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>Q&amp;A</strong>. Your team will be answering live Q&amp;A."
                        "</p>"
                        '<ul class="student-list">'
                        "<li>The moderator will speak the questions selected from chat.</li>"
                        "<li>A designated team member may use the slides in case the judge asks a "
                        "question that refers to a slide.</li>"
                        "<li>Return to the final slide with contact info if your slides are still "
                        "on screen.</li>"
                        "<li>Be ready to respond to questions in case another team member can't "
                        "for whatever reason.</li>"
                        "<li>Avoid indecisions in selecting team members and hesitations when "
                        "responding to questions.</li>"
                        "<li>It is recommended that team members set up a backend communication "
                        "channel (slack, texting, telegram, skype ...) so that they can synchronize "
                        "without double speaking or speaking to each other in the Q&amp;A "
                        "session.</li>"
                        "<li>Thank the Judges - Attendees (optional).</li>"
                        "</ul>"
                        '<p class="student-text">'
                        "Please communicate the designated student for sharing the screen to your "
                        "instructor."
                        "</p>"
                        "</section>"
                        # Section 12: Post Event
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Post Event</h2>'
                        '<p class="student-text">'
                        "<strong>Winners</strong>. At the end of the presentations, the evaluations "
                        "by the judges will be compiled. The Winners will be announced on the I2G "
                        "Home Page about an hour after the end of the presentations (3:30-4pm). "
                        "Winners will receive a certificate in the mail. There are plans to build a "
                        "wall plaque at the School of Engineering, where winners will be added."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>Program Feedback</strong>. We appreciate if you take a moment to "
                        "take this "
                        '<a href="https://ucmerced.az1.qualtrics.com/jfe/form/SV_e4L1PyHidYuThEW" '
                        'target="_blank" rel="noopener noreferrer">'
                        "Post Capstone &amp; I2G survey</a> "
                        "to help us improve the program and experiential learning experience."
                        "</p>"
                        "</section>"
                        # Section 13: Keep in Touch
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Keep in Touch with Alma Mater</h2>'
                        '<p class="student-text">'
                        "<strong>Contact info</strong>. UC Alumni have the benefit of the student "
                        "email address forever: take advantage of this great resource! It is advised "
                        "that you store and forward your email @ucmerced.edu to your personal email, "
                        "unless you plan to check your alumni email in the future: this is a great "
                        "way to be contacted by UC Merced or Alumni in the future."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>LinkedIn</strong>. It is advised that you set up or update your "
                        "LinkedIn account for professional development, and connect to key contacts "
                        "at the School of Engineering and Career Services."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>Jobs and Internships</strong>. Contact your client for job or "
                        "internship opportunities: they are the low hanging fruit in your job search. "
                        "Also, use your Capstone experience with industry in your resume. Some "
                        "Capstone projects may lead to a continuation: check with your partner if "
                        "they are interested in continuing them, or offer to do so with a term job "
                        "or internship. Being enthusiastic, curious and entrepreneurial will help you "
                        "in career building."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>Keep in touch</strong>."
                        "</p>"
                        '<ul class="student-list">'
                        "<li>We look forward to hearing your career moves.</li>"
                        "<li>We are happy to invite you to participate as a Judge to a future "
                        "I2G.</li>"
                        "<li>We solicit that you propose and mentor projects, with the organization "
                        "you work for.</li>"
                        "<li>Please promote the I2G/Capstone program with your employer.</li>"
                        "</ul>"
                        "</section>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "video-preparation",
        "route": "/video-preparation",
        "title": "I2G - Video Presentation Guidelines",
        "page_css_class": "student-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Video preparation guide",
                "data": {
                    "heading": "I2G - Video Presentation Guidelines",
                    "heading_level": 1,
                    "body_html": (
                        # Section 1: Planning for Content
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Planning for Content</h2>'
                        '<p class="student-text">'
                        "Your video presentation will be streamed at the public I2G event and will be "
                        "(optionally, depending on partner approval) available for later download or "
                        "streaming by everyone. Therefore, your video "
                        "<strong>MUST BE APPROVED BY YOUR INDUSTRY PARTNER</strong> for public release."
                        "</p>"
                        '<p class="student-text">Recommendations:</p>'
                        '<ol class="student-ordered-list">'
                        "<li>Ask your industry partner ASAP what content is allowed for public release "
                        "and what content MUST NOT be shown (if any).</li>"
                        "<li>Write the short summary (follow instructions on content upload for your "
                        "class).</li>"
                        "<li>Plan the script and presentation for the video.</li>"
                        "<li>Submit to client for approval.</li>"
                        "<li>Develop your video.</li>"
                        "<li>Submit to client for approval.</li>"
                        "<li>If partner does not approve, revise it till approved.</li>"
                        "</ol>"
                        '<p class="student-text">'
                        "Problems or help? Please contact your instructors or email to: "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>'
                        "</p>"
                        "</section>"
                        # Section 2: Checklist
                        '<section class="student-section">'
                        '<h2 class="student-section-title">Checklist (Technology and Preparation)</h2>'
                        '<ul class="student-list">'
                        "<li>Test Windows Movie Maker, on Mac iMovie (both free) for stitching "
                        "video</li>"
                        "<li>Check if you can run the Zoom Virtual Background on your computer</li>"
                        "<li>Test the approved I2G virtual background: "
                        '<a href="https://ucmerced.box.com/s/rvd24ng4hyptg27rp5cposeo0b8ad6rl" '
                        'target="_blank" rel="noopener noreferrer">Download here</a></li>'
                        "<li>Prepare how to use some pointer to indicate what a speech refers to on "
                        "a slide or a software demo or screen.</li>"
                        "<li>Test audio, and make sure that the volume of all voices will be "
                        "balanced.</li>"
                        "<li>Check for possible background noises that you don't hear but show up "
                        "in zoom recording.</li>"
                        "<li>Use the same equipment setup (computer, microphone, location) that you "
                        "will be using during Innovate to Grow Q&amp;A session.</li>"
                        "<li>Check if camera has any washout.</li>"
                        "<li>Plan ahead about what you want to present, record the content in "
                        "different sessions. Later on just stitch the recordings together: on "
                        "Windows Movie Maker, on Mac iMovie (both free).</li>"
                        "</ul>"
                        "</section>"
                        # Section 3: General Guidelines
                        '<section class="student-section">'
                        '<h2 class="student-section-title">General Guidelines</h2>'
                        '<ul class="student-list">'
                        "<li>When making the video presentation, <strong>consider your "
                        "audience</strong>. In the case of the final presentation your audience is "
                        "technical and/or business oriented: faculty, TAs, industry partners, judges "
                        "etc. The content and delivery should be chosen accordingly.</li>"
                        "<li>Plan for delivering the content within the maximum time allowed (depends "
                        "on the Class - refer to specific guidelines by your instructor).</li>"
                        "<li>Please make sure to <strong>check with your mentor/client all "
                        "materials</strong> for submission regarding confidentiality concerns. You "
                        "must make sure your client agrees with making that information public.</li>"
                        "<li>Please make sure to include the following in your <strong>first and last "
                        "slides</strong>:"
                        '<ul class="student-list">'
                        "<li>The project title as specified by the industry partner.</li>"
                        "<li>Team name chosen by you (follow Guidelines from your Class).</li>"
                        "<li>Your team number (follow Guidelines from your Class).</li>"
                        "<li>Your industry partner information (Company Name).</li>"
                        "<li>List of all your names and (optional but recommended) your contact "
                        "info, or LinkedIn for your professional contact.</li>"
                        "</ul></li>"
                        "<li>Place a footer <strong>in all other slides</strong> with the following "
                        "information:"
                        '<ul class="student-list">'
                        "<li>Team name (and team number in parenthesis).</li>"
                        "<li>Project title &mdash; as specified by the industry partner.</li>"
                        "<li>Industry partner name &mdash; E.g. Veracruz Ventures or Cisco "
                        "Systems.</li>"
                        "<li>Slide number.</li>"
                        "</ul></li>"
                        "<li>In your presentation, include a pause of a couple of seconds in the "
                        "first and last slide to give viewers time to take notes of the information "
                        "being shown.</li>"
                        "<li>In the presentation, remember to end on the last slide with project and "
                        "team info (not on a &quot;Thank you!&quot; or &quot;Questions?&quot; or "
                        "End-of-Presentation-blank-default-screen).</li>"
                        "</ul>"
                        '<p class="student-text">These steps are important because:</p>'
                        '<ol class="student-ordered-list">'
                        "<li>Judges may have to enter your team reference at any time during your "
                        "presentation.</li>"
                        "<li>Potentially interested attendees can note down your contact "
                        "information.</li>"
                        "<li>You have more opportunity to promote yourself.</li>"
                        "</ol>"
                        '<p class="student-text">'
                        "In your video recording, please remember, after your closing statements on "
                        "the last slide of project / team info, to continue the video recording "
                        "<strong>while resting on such last slide mute for 10-15 seconds</strong>. "
                        "This will allow the technical hosts of Zoom to pause the video and start "
                        "the Q&amp;A while on your team's complete info."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>IMPORTANT</strong>: Judges will have an online questionnaire and "
                        "need to input the team name and number when judging the teams. This process "
                        "can (and often does) spill over to the subsequent presentation. This is why "
                        "it is <strong>very important</strong> to keep the context of team number in "
                        "the slides."
                        "</p>"
                        "</section>"
                        # Section 4: Video Production
                        '<section class="student-section">'
                        '<h2 class="student-section-title">'
                        "Video Production and I2G Event Guidelines</h2>"
                        '<ul class="student-list">'
                        "<li>We encourage you to use video editing software to have a polished final "
                        "product. PC users can try Windows Movie Maker while Mac users can try Mac "
                        "iMovie. Both are free to use and allow video splicing and basic editing. "
                        "More powerful features are available in screencasting software such as "
                        '<a href="https://obsproject.com/" target="_blank" rel="noopener noreferrer">'
                        "OBS studio</a>, which is free and compatible with all common operating "
                        "systems. PowerPoint also allows you to record your presentation as an HD "
                        "video including a voiceover.</li>"
                        "<li>You do not need to record live from Zoom. In fact, we encourage you to "
                        "not follow this approach since the quality of the final product is low and "
                        "there may be glitches. Instead, consider having each person record their "
                        "part separately and splicing all contributions together.</li>"
                        "<li>You can also consider having each person record only their voice "
                        "narrating their corresponding sections and then superimpose these over the "
                        "slides in post-production. You can use free software like "
                        '<a href="https://www.audacityteam.org/" target="_blank" '
                        'rel="noopener noreferrer">Audacity</a> to edit/improve your audio '
                        "recordings.</li>"
                        "<li>Test the audio of each person before recording to make sure they are "
                        "all at the same level.</li>"
                        "<li>Please try to use the Zoom virtual background during all your I2G "
                        "video calls. You can find the approved I2G background at: "
                        '<a href="https://ucmerced.box.com/s/rvd24ng4hyptg27rp5cposeo0b8ad6rl" '
                        'target="_blank" rel="noopener noreferrer">Download here</a>.</li>'
                        "<li>If showing yourself in the presentation video or the I2G event, dress "
                        "professionally, as if you were presenting on stage.</li>"
                        "<li>Please use a virtual pointer or some other means (such as PowerPoint "
                        "animations) to indicate to your viewer what you are referring to at any "
                        "moment.</li>"
                        "<li>When recording your presentation, try to use the same equipment setup "
                        "(computer, microphone, location) that you will be using during Innovate to "
                        "Grow Q&amp;A.</li>"
                        "</ul>"
                        "</section>"
                        # Section 5: Do's and Don'ts
                        '<section class="student-section">'
                        "<h2 class=\"student-section-title\">Presentation Do's and Don'ts</h2>"
                        '<h3 class="student-section-subtitle">Do\'s</h3>'
                        '<ul class="student-list">'
                        "<li>Plan ahead for the content of your presentation and its delivery. "
                        "Improvisation is not a method. Plan out what you want to present, and "
                        "record the content in different sessions, and then splice the recordings "
                        "together.</li>"
                        "<li>Clearly explain and focus on the problem/project, and the design and "
                        "value of your specific solution/design (spend minimal time on standard "
                        "stuff, if any).</li>"
                        "<li>Clarify constraints and limitations of the problem-project.</li>"
                        "<li>Describe the problem first, then your solution.</li>"
                        "<li>Make sure when you show a demo of your product, the actual screen of "
                        "the demo is full screen and legible.</li>"
                        "<li>Explain acronyms unless widely known.</li>"
                        "<li>Use the approved I2G virtual background.</li>"
                        "<li>Make sure there is no background noise: alert anyone surrounding you "
                        "to not be making noises when recording starts.</li>"
                        "<li>Make sure the volume of all voices is balanced.</li>"
                        "<li>Use a pointer when talking about certain items in the slides or "
                        "demo.</li>"
                        "<li>When starting the video on the first slide, pause for a couple of "
                        "seconds as audience focuses, then introduce the team and members, then "
                        "industry partner, then the project.</li>"
                        "<li>When ending the video, pause a second on the last slide after "
                        "finishing the presentation, and before closing the video.</li>"
                        "</ul>"
                        '<h3 class="student-section-subtitle">Don\'ts</h3>'
                        '<ul class="student-list">'
                        "<li>Waste time on the history of the client, rather than the value of "
                        "your project.</li>"
                        "<li>Waste time showing standard app stuff like authentication log in and "
                        "out, which diverts attention from unique functionality. Instead, say that "
                        "you are using the secure, state of the art, proven authentication.</li>"
                        "<li>Include in your screencasting your browser showing tabs, toolbars, "
                        "menus etc. taking screen space and showing private information.</li>"
                        "<li>Describe the solution without first explaining the problem.</li>"
                        "<li>Speak in a soft, robotic, or otherwise dull voice. Instead, practice "
                        "ahead of time to ensure a fluid and natural speech.</li>"
                        "<li>Speak without any pauses &mdash; it can be hard to follow.</li>"
                        "<li>Use slang like &quot;to up the quality&quot;. This may work in "
                        "interactive speech, but not in pre-recorded presentations.</li>"
                        "<li>Say something like &quot;This app will only be good for business, not "
                        "for personal use&quot;. Why limit yourself? You don't know the full "
                        "potential.</li>"
                        "<li>Use speech referring to objects on a busy screen. To what are you "
                        "referring?! Use a pointer.</li>"
                        "<li>End with &quot;and ... that's it!&quot;. Instead, it is better to "
                        "&quot;thank&quot; or &quot;call for action&quot;.</li>"
                        "<li>Allow random external sounds to interrupt your video. If someone "
                        "flushes the toilet or a car passes by, simply stop for a few seconds, "
                        "start over from before the interruption, and then delete the bad parts "
                        "using video editing software.</li>"
                        "<li>Say things like &quot;I did this&quot; or &quot;I designed that&quot;. "
                        "This is a team effort. Use &quot;we&quot; all the time.</li>"
                        "<li>Display your slides in edit mode. They look too small and it is "
                        "unprofessional. Make sure your slides are in full screen presentation "
                        "mode when recording.</li>"
                        "<li>Use acronyms that are not obvious to everyone.</li>"
                        "<li>Try to decide in real time who will be speaking next or what you will "
                        "be saying. Plan ahead!!!</li>"
                        "</ul>"
                        "</section>"
                    ),
                },
            },
        ],
    },
    # ==================== BATCH D ====================
    {
        "slug": "privacy",
        "route": "/privacy",
        "title": "I2G Privacy Policy",
        "page_css_class": "privacy-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Privacy policy",
                "data": {
                    "heading": "Privacy Policy",
                    "heading_level": 1,
                    "body_html": (
                        '<p class="privacy-text" style="font-style: italic;">'
                        "Effective Date: Tuesday, January 28, 2025"
                        "</p>"
                        '<p class="privacy-text">'
                        "At Innovate to Grow (I2G), we respect your privacy and are committed to "
                        "protecting your personal information. This Privacy Policy explains how we "
                        "collect, use, and protect information when you interact with our services, "
                        "including text messaging for event-related communications."
                        "</p>"
                        '<h2 class="privacy-section-title">1. Information We Collect</h2>'
                        '<h3 class="privacy-subsection-title">Personal Information</h3>'
                        '<p class="privacy-text">'
                        "When you register for events, sign up for text notifications, or otherwise "
                        "interact with us, we may collect:"
                        "</p>"
                        '<ul class="privacy-list">'
                        "<li>Name</li>"
                        "<li>Email address</li>"
                        "<li>Phone number</li>"
                        "<li>Organization or affiliation</li>"
                        "</ul>"
                        '<h3 class="privacy-subsection-title">Automatically Collected Data</h3>'
                        '<p class="privacy-text">We may collect non-personal information, such as:</p>'
                        '<ul class="privacy-list">'
                        "<li>Device type and operating system</li>"
                        "<li>Browser type</li>"
                        "<li>IP address</li>"
                        "<li>Usage data (e.g., pages visited, time spent on site)</li>"
                        "</ul>"
                        '<h3 class="privacy-subsection-title">Text Message Interaction</h3>'
                        '<p class="privacy-text">'
                        "If you opt in to receive text messages, we collect your phone number and "
                        "records of messages sent and received."
                        "</p>"
                        '<h2 class="privacy-section-title">2. How We Use Your Information</h2>'
                        '<p class="privacy-text">'
                        "We use the information we collect for the following purposes:"
                        "</p>"
                        '<ul class="privacy-list">'
                        "<li><strong>Event Registration:</strong> To process your registration and "
                        "provide event-related updates.</li>"
                        "<li><strong>Two-Factor Authentication (2FA):</strong> To verify your identity "
                        "during login or account actions.</li>"
                        "<li><strong>Event Reminders:</strong> To send event reminders and updates via "
                        "text message.</li>"
                        "<li><strong>Customer Support:</strong> To respond to your inquiries and "
                        "provide support.</li>"
                        "<li><strong>Legal Compliance:</strong> To comply with applicable laws and "
                        "regulations.</li>"
                        "</ul>"
                        '<h2 class="privacy-section-title">'
                        "3. Your Consent for Receiving Text Messages</h2>"
                        '<p class="privacy-text">'
                        "By providing your phone number and opting in to receive text messages, you "
                        "consent to receive messages from I2G related to event updates, reminders, and "
                        "two-factor authentication."
                        "</p>"
                        '<ul class="privacy-list">'
                        "<li>You can opt out at any time by replying <strong>STOP</strong> to any "
                        "message.</li>"
                        "<li>For help, reply <strong>HELP</strong> or contact us at "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.</li>'
                        "<li>Message frequency may vary depending on event schedules.</li>"
                        "<li>Message and data rates may apply.</li>"
                        "</ul>"
                        '<h2 class="privacy-section-title">4. Sharing Your Information</h2>'
                        '<p class="privacy-text">'
                        "We do not sell your personal information. We may share your data in the "
                        "following cases:"
                        "</p>"
                        '<ul class="privacy-list">'
                        "<li><strong>Service Providers:</strong> We use third-party services like "
                        "Twilio for text messaging. These providers are bound by their own privacy "
                        "policies and data protection agreements.</li>"
                        "<li><strong>Legal Compliance:</strong> We may disclose information if "
                        "required by law or to protect our rights.</li>"
                        "</ul>"
                        '<h2 class="privacy-section-title">5. Data Retention</h2>'
                        '<p class="privacy-text">'
                        "We retain your personal information for as long as necessary to fulfill the "
                        "purposes outlined in this policy or as required by law. If you opt out of text "
                        "messages, your phone number will be removed from our messaging list, though "
                        "records may be retained for compliance purposes."
                        "</p>"
                        '<h2 class="privacy-section-title">6. Your Rights</h2>'
                        '<p class="privacy-text">'
                        "You have the following rights regarding your personal data:"
                        "</p>"
                        '<ul class="privacy-list">'
                        "<li><strong>Opt-Out:</strong> Reply <strong>STOP</strong> to any text message "
                        "to unsubscribe.</li>"
                        "<li><strong>Access and Update:</strong> Contact us to access or update your "
                        "personal information.</li>"
                        "<li><strong>Data Deletion:</strong> Request the deletion of your personal "
                        "data by emailing "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.</li>'
                        "</ul>"
                        '<h2 class="privacy-section-title">7. Security</h2>'
                        '<p class="privacy-text">'
                        "We implement reasonable security measures to protect your information. "
                        "However, no method of data transmission or storage is completely secure, and "
                        "we cannot guarantee absolute security."
                        "</p>"
                        '<h2 class="privacy-section-title">8. Children\'s Privacy</h2>'
                        '<p class="privacy-text">'
                        "Our services are not intended for children under 13. We do not knowingly "
                        "collect personal information from children under 13. If we become aware that "
                        "a child has provided us with personal data, we will take steps to delete it."
                        "</p>"
                        '<h2 class="privacy-section-title">9. Contact Us</h2>'
                        '<p class="privacy-text">'
                        "If you have any questions about this Privacy Policy, please contact us at:"
                        "</p>"
                        '<ul class="privacy-list">'
                        "<li><strong>Email:</strong> "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a></li>'
                        "</ul>"
                        '<h2 class="privacy-section-title">10. Changes to This Privacy Policy</h2>'
                        '<p class="privacy-text">'
                        "We may update this Privacy Policy from time to time. Any changes will be "
                        "posted on this page with an updated effective date. We encourage you to "
                        "review this policy periodically to stay informed about how we are protecting "
                        "your information."
                        "</p>"
                        '<h2 class="privacy-section-title">I2G Messaging Terms and Conditions</h2>'
                        '<h3 class="privacy-subsection-title">Program Name</h3>'
                        '<p class="privacy-text">I2G Event Messaging</p>'
                        '<h3 class="privacy-subsection-title">Program Description</h3>'
                        '<p class="privacy-text">'
                        "I2G uses text messaging to send event reminders, updates, and two-factor "
                        "authentication codes to registered participants."
                        "</p>"
                        '<h3 class="privacy-subsection-title">Opt-Out</h3>'
                        '<p class="privacy-text">'
                        "You can opt out of receiving text messages at any time by replying "
                        "<strong>STOP</strong> to any message. After opting out, you will receive a "
                        "confirmation message and will no longer receive texts from I2G."
                        "</p>"
                        '<h3 class="privacy-subsection-title">Customer Support</h3>'
                        '<p class="privacy-text">'
                        "For support, reply <strong>HELP</strong> to any message or email us at "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.'
                        "</p>"
                        '<h3 class="privacy-subsection-title">Message Delivery</h3>'
                        '<p class="privacy-text">'
                        "Message frequency varies based on event schedules and account activity. "
                        "Messages may include event reminders, updates, and authentication codes."
                        "</p>"
                        '<h3 class="privacy-subsection-title">Message and Data Rates</h3>'
                        '<p class="privacy-text">'
                        "Standard message and data rates may apply, depending on your mobile carrier "
                        "and plan."
                        "</p>"
                        '<h3 class="privacy-subsection-title">Privacy</h3>'
                        '<p class="privacy-text">'
                        "Your privacy is important to us. Please review our Privacy Policy above for "
                        "details on how we collect, use, and protect your information."
                        "</p>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "ferpa",
        "route": "/ferpa",
        "title": "FERPA Agreement",
        "page_css_class": "student-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "FERPA agreement",
                "data": {
                    "heading": "FERPA Agreement",
                    "heading_level": 1,
                    "body_html": (
                        '<section class="student-section">'
                        '<h2 class="student-section-title" style="text-align: center;">'
                        "Student Presentation Permission and FERPA Release</h2>"
                        '<p class="student-text">'
                        "I hereby grant to The Regents of the University of California, on behalf of "
                        "the Merced campus, permission to record by means of audio-visual analog "
                        "and/or digital medium the presentation, lecture(s), interviews, and related "
                        "materials I will prepare and present as part of Innovate to Grow "
                        "(&quot;Presentation&quot;) and to reproduce the Presentation, including any "
                        "written materials or visual aid utilized during the Presentation, my name, "
                        "likeness, identity, voice, photographic image, videographic image and oral or "
                        "recorded statements (hereafter &quot;Related Appearance&quot;) for research or "
                        "educational use subject to the following restrictions:"
                        "</p>"
                        '<ol class="student-ordered-list">'
                        "<li>The Presentation and Related Appearance will be utilized for the program "
                        "listed above only. The material will be available online via a video stream "
                        "which may be accessed by UC Merced staff, faculty, and the general "
                        "public.</li>"
                        "<li>The Presentation and Related Appearance will be available online during "
                        "the event and will be subsequently archived for reuse.</li>"
                        "<li>UC Merced will use the Presentation and Related Appearance for "
                        "educational purposes only and not for any commercial/promotional purposes or "
                        "activities.</li>"
                        "</ol>"
                        '<p class="student-text">'
                        "By signing this form, I waive and release The Regents of the University of "
                        "California and its officers, agents and employees, from any claim or liability "
                        "relating to the use of the Presentation and Related Appearance in conformance "
                        "with the restrictions stated above."
                        "</p>"
                        '<p class="student-text">'
                        "<strong>FERPA RELEASE</strong>: I understand that the media may be protected "
                        "by the Federal Educational Rights and Privacy Act (&quot;FERPA&quot;) as "
                        "educational records. I hereby consent to the disclosure of the presentation "
                        "by the University to faculty, staff, students, and visitors of the University, "
                        "which may include the general public. The purpose of this disclosure is to "
                        "advance the educational mission of the University."
                        "</p>"
                        '<p class="student-text">'
                        "This Agreement shall be governed by and interpreted in accordance with the "
                        "laws of the State of California. This Agreement expresses the complete "
                        "understanding of the parties with respect to the subject matter and supersedes "
                        "all prior representations and understandings."
                        "</p>"
                        '<p class="student-text">'
                        "I acknowledge that The Regents of the University of California will rely on "
                        "this permission and release in producing and distributing the Presentation and "
                        "the Related Appearance."
                        "</p>"
                        '<p class="student-text">'
                        "I am an adult, 18 years or older, and I have read and understand this "
                        "agreement and I freely and knowingly give my consent to The Regents of the "
                        "University of California, on behalf of the Merced campus, as described herein."
                        "</p>"
                        "</section>"
                        '<section class="student-section">'
                        '<p class="student-text">'
                        "<strong>If individual photographed/recorded is under eighteen (18) years old, "
                        "the following section must be completed:</strong> "
                        "I have read and I understand this document. I understand and agree that it is "
                        "binding on me, my child (named above), our heirs, assigns and personal "
                        "representatives. I acknowledge that I am eighteen (18) years old or more and "
                        "that I am the parent or guardian of the child named above."
                        "</p>"
                        "</section>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "student-agreement",
        "route": "/student-agreement",
        "title": "I2G Project - Student Agreement",
        "page_css_class": "student-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Student agreement",
                "data": {
                    "heading": "I2G Project - Student Agreement",
                    "heading_level": 1,
                    "body_html": (
                        '<section class="student-section">'
                        '<p class="student-text">'
                        "<strong>UC MERCED INNOVATE TO GROW - STUDENT PARTICIPATION ACKNOWLEDGMENT AND "
                        "IP+NON-DISCLOSURE AGREEMENT</strong>"
                        "</p>"
                        '<p class="student-text">'
                        "In consideration of the opportunity to participate in the Innovate to Grow "
                        "Program (hereafter referred to as &quot;I2G&quot;) for credit at the "
                        "University of California, Merced, (hereafter referred to as "
                        "&quot;UCM&quot;), I hereby acknowledge and agree to the following:"
                        "</p>"
                        '<ol class="student-ordered-list">'
                        "<li>As part of I2G, UCM's undergraduate engineering students have the "
                        "opportunity to undertake an industrial project, referred to as &quot;I2G "
                        "Project,&quot; and to learn as part of a team that includes practicing "
                        "engineers and other professionals from partner organizations "
                        "(&quot;Partners&quot;). The I2G teams focus on engineering design projects "
                        "that are purposefully chosen for their potential for significant near-term "
                        "impact on the communities, organizations, and/or industries in the region "
                        "and beyond.</li>"
                        "<li>Participation in the UCM I2G Program is voluntary and is subject to "
                        "certain participation requirements as described below. I have the opportunity "
                        "to undertake a traditional project (hereafter referred to as &quot;Academic "
                        "Project&quot;) that would satisfy the UCM requirements. The Academic Project "
                        "would not involve the assignment of any intellectual property that I may "
                        "develop as part of an I2G Project. Before I chose the I2G option, I may seek "
                        "advice regarding the advantages and disadvantages of both types of projects, "
                        "including advice regarding the assignment of any rights to intellectual "
                        "property developed as part of the I2G Project.</li>"
                        "<li>I understand that as a result of my work on an I2G Project, intellectual "
                        "property in the form of inventions, data, formulae, computer software "
                        "specifications, products, processes, technologies, patents, copyrights, and "
                        "other technical and product information (&quot;Intellectual Property&quot;) "
                        "may be developed during the project and that such Intellectual Property may "
                        "have commercial value.</li>"
                        "<li>I understand that UCM and the I2G Partners with which I may work on an "
                        "I2G Project have entered into a relationship to work jointly on an I2G "
                        "Project proposed by the Partners. This relationship is reflected in a "
                        "document that specifies that the Partners may require assignment of all "
                        "intellectual property created as a result of the project as a condition of "
                        "student participation on its project (&quot;Partner "
                        "Acknowledgement&quot;).</li>"
                        "<li>I acknowledge that as a condition of my voluntary participation on an "
                        "I2G Project, prior to the commencement of such I2G Project, I assign to the "
                        "Partner a non-exclusive, transferable, sub-licensable, royalty-free, "
                        "worldwide license to use the Intellectual Property that I developed as part "
                        "of the I2G Project. I also acknowledge that the Partner may require me to "
                        "assign all my rights and ownership interest in such Intellectual Property "
                        "created as a result of and during my participation in the I2G Project. I "
                        "agree to cooperate with the Partner, its assignee or designee in perfecting "
                        "rights to such Intellectual Property, for example, by signing any documents "
                        "that may be necessary to perfect the rights. I also acknowledge that I would "
                        "not be entitled to receive any income from the sale or licensing of this "
                        "Intellectual Property by the Partner, and that the Partner may or may not "
                        "reward me in any way, according to the Partner's discretion. I further "
                        "understand that I am likely to be required to obtain express authorization "
                        "from the Partner to publish the results of my I2G Project, except in "
                        "connection with any presentations or reports prepared for educational "
                        "purposes as part of the I2G Program. If I choose not to assign any right or "
                        "interest I have in any Intellectual Property, I understand that I will not "
                        "be eligible to participate in an I2G Project and that I will be provided the "
                        "opportunity to participate in an Academic Project that will provide an "
                        "equivalent educational opportunity.</li>"
                        "<li>I acknowledge and agree that as part of my participation in the I2G "
                        "Program, I may receive information that is marked as or otherwise considered "
                        "confidential or proprietary, or is otherwise subject to restrictions on "
                        "disclosure, and I will not, without express written consent of the owner of "
                        "such confidential or proprietary information, 1) disclose or publish any "
                        "part of such information to others for a period of five (5) years from "
                        "receiving the information; 2) make any use of such information for a five "
                        "(5) year period except in the course of my participation in the UCM I2G "
                        "Program. However, I further understand that I shall not be prevented from "
                        "disclosing information when I can establish, by competent evidence, that "
                        "such information:"
                        "<ul>"
                        "<li>Was already known to me at the time of disclosure by Partner or a third "
                        "party collaborator; or</li>"
                        "<li>Was available to the public or otherwise was part of the public domain "
                        "at the time of disclosure by Partner or a third party collaborator; or</li>"
                        "<li>Became available to the public or otherwise became part of the public "
                        "domain after the time of disclosure by Partner or a third party "
                        "collaborator, but other than through my own acts or omissions in violation "
                        "of this Agreement; or</li>"
                        "<li>Was lawfully disclosed to me by a party not collaborating with Partner "
                        "subsequent to the time of disclosure by Partner or a third party "
                        "collaborator.</li>"
                        "</ul></li>"
                        "<li>I acknowledge that as a condition of my voluntary participation on an "
                        "I2G Project, prior to the commencement of such I2G Project, I may be "
                        "required by the Partner, or a third party collaborating with the Partner, "
                        "to enter into a binding non-disclosure agreement. If I choose not to enter "
                        "into a non-disclosure agreement, I understand that I will not be eligible "
                        "to participate in an I2G Project and that I will be provided the opportunity "
                        "to participate in an Academic Project that will provide an equivalent "
                        "education opportunity.</li>"
                        "<li>As a condition of being permitted to participate in any way in the I2G "
                        "Program, I, for myself, my heirs, personal representatives, or assigns, do "
                        "hereby release, waive, discharge and covenant not to sue The Regents of the "
                        "University of California, its officers, employees, and agents from liability "
                        "from any and all claims, including claims of negligence on the part of The "
                        "Regents of the University of California, its officers, employees, and "
                        "agents, resulting in personal injury, accidents or illnesses (including "
                        "death) and property loss arising from participation in the I2G Program. "
                        "Participation in the I2G Program carries with it inherent risks that cannot "
                        "be eliminated regardless of the care taken to avoid injury and I hereby "
                        "assert that my participation in the I2G Program is voluntary and I knowingly "
                        "assume all such risks. I know and understand and appreciate these and other "
                        "risks, and in signing this waiver of liability and assumption of risk, I "
                        "understand that I am giving up substantial rights, including my right to "
                        "sue.</li>"
                        "<li>I agree to comply with all of the rules and conditions of participating "
                        "in the I2G Program. I certify that I have adequate health insurance "
                        "necessary to provide for and pay any medical costs that may directly or "
                        "indirectly result from my participation in the project. I am aware that if "
                        "I provide a vehicle not owned and operated by the University for "
                        "transportation to, at, or from the project sites, or if I am a passenger in "
                        "such a vehicle, the University is not responsible for any damage caused by "
                        "or arising from my use of such transportation.</li>"
                        "<li>Immediately upon completion of the I2G Project, I agree to provide UCM "
                        "with all software, records, project notebooks, memoranda, information, data, "
                        "programs, models and equipment of any nature in my possession or under my "
                        "control pertaining to the I2G Project, for purposes of academic evaluation "
                        "of my participation on the project. These materials will be returned to me "
                        "following completion of the academic evaluation; however, UCM may retain "
                        "copies of such materials for its records and other educational purposes. I "
                        "also understand that these materials may be considered confidential by "
                        "Partners and as such be subject to paragraph 6 above.</li>"
                        "</ol>"
                        "</section>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "sponsor-acknowledgement",
        "route": "/sponsor-acknowledgement",
        "title": "I2G Project Sponsor Acknowledgement",
        "page_css_class": "acknowledgement-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "Sponsor acknowledgement",
                "data": {
                    "heading": "I2G Project Sponsor Acknowledgement",
                    "heading_level": 1,
                    "body_html": (
                        '<p style="text-align: center;">'
                        "<strong>University of California, Merced - School of Engineering - Innovate "
                        "to Grow Program</strong>"
                        "</p>"
                        '<p style="text-align: center;">'
                        "<strong>Partner Acknowledgement</strong>"
                        "</p>"
                        "<h2>Summary</h2>"
                        "<p><em>Partner</em>:</p>"
                        "<ul>"
                        "<li>Partner must assign a knowledgeable liaison/mentor for the project "
                        "duration.</li>"
                        "<li>The liaison/mentor must be present at project kick-off to provide a "
                        "thorough understanding of the project goals. Without sufficient information "
                        "students may be unable to move forward quickly. (After kick-off the when "
                        "and how of interactions can be discussed with the team).</li>"
                        "<li>If Partner is unresponsive or decides to pull-out in the middle of a "
                        "project, it accepts that students can continue on that project, otherwise "
                        "they may be affected significantly, both academically and financially.</li>"
                        "</ul>"
                        "<p><em>Students</em>:</p>"
                        "<ul>"
                        "<li>Students will digitally sign agreements (NDA and IP licensing) to the "
                        "Partners, before accessing the list of partner projects.</li>"
                        "<li>Students unwilling to do so will be assigned to a project that does not "
                        "require NDA or IP assignment to Partner.</li>"
                        "</ul>"
                        "<p><em>UC Merced</em>:</p>"
                        "<ul>"
                        "<li>UCM matches students with approved Partner projects, forming teams.</li>"
                        "<li>UCM does not retain IP. See student section above.</li>"
                        "<li>UCM does not guarantee delivery of results, and requires liability "
                        "indemnification.</li>"
                        "<li>UCM does not require payment as a condition to run a Partner project, "
                        "but seeks and appreciates donations to sustain the program.</li>"
                        "</ul>"
                        "<p><em>Notice</em>: Special circumstances can be discussed during the course "
                        "of the project to ensure success for all parties involved (Win-Win-Win). This "
                        "includes specific project requirements such as confidentiality, IP, access to "
                        "facilities, material and equipment costs, levels of support to the program, "
                        "etc.</p>"
                        "<h2>I2G Program Background</h2>"
                        "<p>Thank you for your interest in supporting UC Merced's Innovate to Grow "
                        "(I2G) Program. The primary objective of the Program is to provide UC Merced "
                        "(UCM) undergraduate students with the opportunity to learn as part of a team "
                        "that includes practicing engineers and other professionals from partner "
                        "organizations like yours (Partner). I2G projects are undertaken by students "
                        "from engineering and other participating majors as the final part of their "
                        "degree requirements. The I2G teams focus on design projects with engineering "
                        "content that are chosen purposefully based on their potential for desirable "
                        "near-term impact on Partners' needs/goals. As such, the commitment of the "
                        "teams and partners greatly enhances the quality of the design experience over "
                        "traditional academic projects required by accredited engineering degree "
                        "curricula. It adds significant professional training with real-world "
                        "implications for the students. Your mentorship of I2G students in addition to "
                        "financial and resource commitment will support and enhance UCM's educational "
                        "mission and the experience of its students.</p>"
                        "<p>Since I2G is an educational program, UCM does not retain intellectual "
                        "property (IP), and does not guarantee completion of any project or delivery of "
                        "any project results, although based on previous experience we expect a high "
                        "level of effort and productivity from our students. It is important that you "
                        "understand that the I2G Program is an academic program designed to meet the "
                        "requirements of the students' academic program and that any benefit to the "
                        "Partner in terms of the outcome of the research is an important, yet secondary, "
                        "purpose and objectives of the Program.</p>"
                        "<p>The remainder of this acknowledgement form explains the details of the "
                        "Partners' collaboration in I2G and its Projects. We ask that you acknowledge "
                        "your understanding of the purpose and elements of the I2G Program.</p>"
                        "<p><strong>1. Project Mentorship and Liaison Expectations</strong></p>"
                        "<p>The sponsoring organization is requested to identify an employee of your "
                        "organization to act as liaison/mentor for your project(s). This liaison/mentor "
                        "should plan to meet (in person or via teleconference) with students assigned to "
                        "your project(s) on a regular basis, and with UCM faculty responsible for "
                        "academic supervision of the project(s) as necessary. The interaction between "
                        "the liaison/mentor and the team is advised on a weekly or bi-weekly basis to "
                        "answer questions and ensure team progress.</p>"
                        "<p>Notice: It is important that the Partner's liaison/mentor responds promptly "
                        "to the students at the beginning of the semester to provide detail and "
                        "clarifications about the project and its objectives, so that the team begins "
                        "the project quickly and in the right direction. Communications thereafter can "
                        "be arranged between the mentor and team.</p>"
                        "<p><strong>2. Intellectual Property</strong></p>"
                        "<p>Students participating in the I2G Program are not employees of the "
                        "University. Per UC's Patent Policy, the University will not own any patentable "
                        "ideas and inventions, copyrights, data, or other intellectual property "
                        "developed by students while performing a I2G Project.</p>"
                        '<p>The <a href="/student-agreement">I2G Student Agreement</a> that students '
                        "sign to participate in a sponsored I2G Project includes the provision to "
                        "assign to its sponsor a non-exclusive, transferable, sub-licensable, "
                        "royalty-free, worldwide license to use the intellectual property developed as "
                        "part of the I2G Project.</p>"
                        "<p>If a student does not wish to execute an assignment of rights, the student "
                        "will have the opportunity to work on an alternative or academic project that "
                        "does not require IP assignment, and another student will be assigned to the "
                        "sponsored I2G Project.</p>"
                        "<p>UCM employees, including faculty and staff, will not participate as part of "
                        "the project except in the capacity as academic advisors to the student "
                        "participants.</p>"
                        "<p><strong>3. Financial Expectations</strong></p>"
                        "<p>A financial commitment is not mandatory. However, we welcome and encourage "
                        "donations to the UC Merced School of Engineering I2G program. Such funds enable "
                        "the School to support this program, including all associated initiatives and "
                        "events. If your organization would like to make a tax-deductible charitable "
                        "gift to support operation of the overall Program you may "
                        '<a href="https://securelb.imodules.com/s/1650/index.aspx?sid=1650&amp;gid=1&amp;pgid=474&amp;utm_source=give_now_button&amp;utm_medium=give_now_button&amp;utm_campaign=uc_merced_giving" '
                        'target="_blank" rel="noopener noreferrer">click here to donate now</a> or '
                        "contact the UC Merced Staff for additional information ("
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>). UCM will use gifts '
                        "from you and other sponsors to cover the general costs and expenses associated "
                        "with the I2G Program and Event (including staff time, engineering and "
                        "administrative support, UC's standard 5 percent gift assessment, travel by "
                        "students and staff to partner sites for visits / presentations, parts and "
                        "expendable supplies for projects, and competition prizes).</p>"
                        "<p>The School provides each Team with a basic budget for material and travel. "
                        "However, if a proposed project exceeds the available University resources "
                        "needed to study, design, prototype or test the solution, then we encourage you "
                        "to propose an alternative or revised project with corresponding resource "
                        "budgets, or to provide additional resources to support the objectives of the "
                        "project. If it is anticipated that any of your projects will incur any "
                        "extraordinary expenses (for example specialized equipment), necessary "
                        "arrangements will be negotiated in advance of the commencement of work on your "
                        "project and will be subject to a specific written agreement of UCM and your "
                        "organization.</p>"
                        "<p><strong>4. I2G Projects Suitability and Students Assignment</strong></p>"
                        "<p>We anticipate that your organization may wish to propose one or more "
                        "projects that address your organization's needs or problems, seeking viable "
                        "design solutions developed by our student teams that may be deployed (see "
                        "Intellectual property section). UCM will work with you to define or refine a "
                        "problem/project statements that are simultaneously suitable for an I2G Project "
                        "per professional degree requirements, policies, and departmental standards. As "
                        "the I2G Projects progress, we will continue to work together to address any "
                        "desired changes to projects.</p>"
                        "<p>UCM will assign a group of undergraduate engineering and other students to "
                        "a project, if there are enough students with expertise/majors that elect to "
                        "participate in the project. If there is no match, the project may be "
                        "reconsidered for execution in the following semester.</p>"
                        "<p><strong>5. Presentations, Confidentiality</strong></p>"
                        "<p>The University is committed to maintaining an open academic environment that "
                        "fosters intellectual creativity. Please be aware that the students and advising "
                        "faculty members will freely discuss all non-confidential information associated "
                        "with your project as part of the normal educational activities of the Program. "
                        "As part of I2G Projects, the students will make various reports and "
                        "presentations to other members of the I2G Program as part of the educational "
                        "experience. Students also may wish to include information about their I2G "
                        "Projects in their resumes, applications and other documents.</p>"
                        "<p>We realize that the students working on your project may come into contact "
                        "with your proprietary or confidential information in the course of the project. "
                        "Therefore, all students participating in the I2G Program execute a general "
                        "non-disclosure agreement (NDA) relating to confidential and proprietary "
                        "information prior to their participation in the Program (included in the "
                        '<a href="/student-agreement">I2G Student Agreement</a>). If you wish to have '
                        "the participants undertaking your project execute a specific non-disclosure "
                        "agreement of your organization, you should provide a copy of your organization "
                        "NDA prior to disclosing confidential information to the participants, and send "
                        "a copy to "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>. If a student does not '
                        "wish to execute your NDA, the student will have the opportunity to work on "
                        "another project and another student will be assigned to your project. Please "
                        "keep in mind that during the course of your project, you will need to clearly "
                        "identify for students what constitutes or is likely to constitute proprietary "
                        "or confidential information.</p>"
                        "<p>Your organization hereby releases the University, its officers, employees, "
                        "students and agents from any and all liability, loss, expense (including "
                        "reasonable attorneys' fees), or claims for injury or damages arising out of the "
                        "released parties' disclosure of any proprietary or confidential information, "
                        "except to the extent the released party intentionally disclosed information "
                        "that such released party knew to be proprietary/confidential. The foregoing "
                        "release shall not limit your right to obtain legally permissible relief "
                        "pursuant to the terms of any NDA entered into directly between you and any "
                        "student, faculty or staff.</p>"
                        "<p><strong>6. No Warranties</strong></p>"
                        "<p>The University makes no warranties, express or implied, as to the condition, "
                        "accuracy, originality, merchantability, or fitness for purposes of any "
                        "products, processes or intellectual property developed in the I2G Program.</p>"
                        "<p><strong>7. No License Granted</strong></p>"
                        "<p>Other than as may be required to implement the I2G Program as part of the "
                        "educational experience of UCM students, this acknowledgement does not "
                        "constitute a grant of license, either implied or express, of any intellectual "
                        "property owned or acquired by your organization, to the University, or anyone "
                        "associated therewith, including its officers, employees, students and agents. "
                        "UCM has the right to retain non-confidential items relating to your project for "
                        "educational purposes, including copies of any software, records, project "
                        "notebooks, memoranda, information, data, programs, models and equipment.</p>"
                        "<p><strong>8. Compliance with All Laws</strong></p>"
                        "<p>All work on your project must be carried out in compliance with federal and "
                        "state laws and regulations and applicable policies (i.e., University policies "
                        "and/or your organization's policies), including laws, regulations and policies "
                        "relating to environmental and occupational health and safety. Your organization "
                        "and UCM are responsible for ensuring such compliance in their respective "
                        "facilities.</p>"
                        "<p><strong>9. Affiliation Agreement and Release of Liability</strong></p>"
                        "<p>We assume that your organization may have an affiliation agreement and/or "
                        "release of liability that you require individuals working in your facilities to "
                        "execute before entering the facility or commencing work. For that reason, we "
                        "will inform all students who are assigned to the I2G Program of this "
                        "likelihood. You should provide a copy of the requested affiliation agreement "
                        "and/or release of liability for signature to the students selected to work on "
                        "your project before entering your facilities, and send a copy to "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>. If the student does '
                        "not wish to execute the affiliation agreement or release, the student will be "
                        "moved to an alternative UCM academic project and another student will be "
                        "assigned to your project.</p>"
                        "<p><strong>10. Release of Liability and Indemnification</strong></p>"
                        "<p>In consideration of your participation in the I2G Program, you agree to "
                        "release the University, its officers, employees, students and agents, from any "
                        "claims arising out of the originality, design, manufacture, or use of any of "
                        "the products, processes, technologies, or intellectual property generated as a "
                        "result of the project, unless such claims arise out of the willful misconduct "
                        "or gross negligence of UC Merced, its officers, employees, students and agents. "
                        "You agree that the University will not be liable for incidental or "
                        "consequential damages, or for loss of profits, resulting from the work "
                        "undertaken on your project or any breach of this agreement.</p>"
                        "<p><strong>11. Use of Name</strong></p>"
                        "<p>Please understand that California law restricts the use of University of "
                        "California names and trademarks. Therefore, if you have the need to use these "
                        "names and trademarks in connection with this collaboration, you will need to "
                        "submit a written request for the University's approval. Please be aware that "
                        "the names and trademarks of the University may not be used for any commercial "
                        "purpose. UCM will request your approval before using your name and "
                        "trademarks.</p>"
                        "<p><strong>12. Term</strong></p>"
                        "<p>While you may terminate your participation in the I2G Project by providing "
                        "UCM with at least thirty (30) days prior written notice, however, please be "
                        "aware that early termination will have a significant effect on the students' "
                        "academic program. We encourage you to explore with UCM ways to complete the "
                        "project before terminating your participation. In order to ensure that the "
                        "students' academic experience is not adversely affected, the University "
                        "reserves the right to continue the project to the extent possible to allow the "
                        "student to complete their program. In this event, the students may or may not "
                        "share the results or outcomes of the project with you, in their sole "
                        "discretion.</p>"
                        "<h2>Acknowledgement</h2>"
                        "<p>If the terms of this letter meet your approval, please acknowledge your "
                        "organization's participation subject to the expectations and terms of the I2G "
                        "Program.</p>"
                        "<p>Your acknowledgement may be executed in one of the following ways:</p>"
                        "<p><strong>Project submission system:</strong> accepting these terms by "
                        "submitting a project in the "
                        '<a href="/project-submission">I2G project submission system</a>.</p>'
                        "<p><strong>Email acknowledgement:</strong> express your acknowledgement in an "
                        "email, in response to the email your organization received containing your "
                        "project(s) information along with all IP+NDA Agreements of the Students "
                        "working on your project(s).</p>"
                        "<p><strong>Signed acknowledgement:</strong> sign or digitally sign a copy of "
                        "this document, and send a scanned copy or PDF to "
                        '<a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.</p>'
                        "<p>We appreciate your support of and participation in the I2G Program and look "
                        "forward to your collaboration with our students.</p>"
                    ),
                },
            },
        ],
    },
    {
        "slug": "sponsors-archive-2014",
        "route": "/sponsors/2014",
        "title": "2014 Sponsors",
        "page_css_class": "sponsors-archive-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "2014 sponsors",
                "data": {
                    "heading": "2014 Sponsors",
                    "heading_level": 1,
                    "body_html": (
                        '<img class="sponsors-archive-image" '
                        'src="/media/sponsors/140424_innovatetogrow_sponsors.jpg" '
                        'alt="2014 Sponsors" width="800" height="600" loading="lazy" />'
                    ),
                },
            },
        ],
    },
    {
        "slug": "sponsors-archive-2015",
        "route": "/sponsors/2015",
        "title": "2015 Sponsors",
        "page_css_class": "sponsors-archive-page",
        "blocks": [
            {
                "block_type": "rich_text",
                "sort_order": 0,
                "admin_label": "2015 sponsors",
                "data": {
                    "heading": "2015 Sponsors",
                    "heading_level": 1,
                    "body_html": (
                        "<p>UC Merced is honored to acknowledge sponsors for commitment to and "
                        "partnership with our programs. Recognition includes acknowledgement in all "
                        "publicity materials, fliers and posters, all email announcements and in media "
                        "releases and publications of the Innovate to Grow competition.</p>"
                        '<img class="sponsors-archive-image" '
                        'src="/media/sponsors/140424_innovatetogrow_sponsors_web.jpg" '
                        'alt="2015 Sponsors" width="800" height="600" loading="lazy" />'
                    ),
                },
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Seed CMS pages for Batch C (judges, attendees, submission, proposals, event/video prep) and Batch D (legal, archive)."

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
