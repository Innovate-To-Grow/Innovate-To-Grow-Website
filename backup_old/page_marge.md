# The old system

## Menu Bar

```
Home -> /
About -> /about
About / Engineering Capstone -> /engineering-capstone
About / Eng. Service Learning -> 外链 https://engineeringservicelearning.ucmerced.edu/
About / Software Eng. Capstone -> /software-capstone
Events -> /event
Events / Registration -> /membership/events
Events / Registration redirect -> /membership/events/<event_name>
Events / Event Info -> /event
Events / Schedule -> /schedule
Events / Projects & Teams -> /projects-teams
Events / for Judges -> /judges
Events / for Attendees -> /attendees
Events / for Students -> /students
Events / Partners & Sponsors -> /acknowledgement
Events / Past Events -> /past-events
Projects -> /projects
Projects / Past Projects -> /past-projects
Projects / Current Projects -> /current-projects
Projects / Project Submission -> /project-submission
Projects / Sample Project Proposals -> /sample-proposals
Partner with Us -> /partnership
Partner with Us / Newsletter -> /membership/signup
Partner with Us / Update I2G Membership -> /membership/update
Partner with Us / Event Registration -> /membership/events
Partner with Us / Propose a project -> /project-submission
Partner with Us / Sign up to Judge -> /judges
Partner with Us / Sponsor or donate -> /sponsorship
Partner with Us / FAQs -> /FAQs
Submit a Project -> /project-submission
Students -> /students
Students / Student Agreement -> /I2G-student-agreement
Students / FERPA (Media) Agreement -> /ferpa
Students / Event preparation -> /i2g-students-preparation
Students / Video preparation -> /video-preparation
Students / Purchasing | Travel -> /capstone-purchasing-reimbursement
```

## pages (Need to Work on)

### Already on the new system

#### Home Page (ignore with new content management system)
/ -> home-pre-event.html
/home-during-event -> home-during-event.html
/home-post-event -> home-post-event.html

#### other statis page (already on the new system with content management system)
/about -> about.html

/engineering-capstone -> engineering-capstone.html
/about_EngSL -> about_EngSL.html
/software-capstone -> software-capstone.html
/FAQs -> faq.html
/project-submission -> project-submission.html
/sample-proposals -> sample-proposals.html
/I2G-student-agreement -> I2G-student-agreement.html
/ferpa -> ferpa.html
/judges -> judges.html
/attendees -> attendees.html
/students -> students.html
/acknowledgement -> acknowledgement.html
/privacy -> terms_and_conditions.html
/contact-us -> contact-us.html
/judging -> judging.html
/capstone-purchasing-reimbursement -> capstone-purchasing-reimbursement.html
/template-email-team-students -> template-email-team-students.html
/I2G-project-sponsor-acknowledgement -> I2G-project-sponsor-acknowledgement.html

/i2g-students-preparation -> i2g-students-preparation.html
/video-preparation -> video-preparation.html

/partnership -> partnership.html
/sponsorship -> sponsorship.html

#### New Project Management System (NEED TO WORK WITH DATA SYNC)
/projects -> projects.html
/current-projects -> current-projects.html
/past-projects -> past-projects.html
/past-projects/<uuid_string> -> past-projects.html
/past-events -> past-events.html


### NEED TO WORK
/template -> template.html >>> This Page is not work on the old system

work with layout issue


### NEED TO WORK WITH NEW CONTENT MANAGEMENT SYSTEM
/event -> event.html
/schedule -> schedule.html
/projects-teams -> projects-teams.html

### past sponsors page
/2014-sponsors -> 2014-sponsors.html
/2015-sponsors -> 2015-sponsors.html

### past event page
/2025-fall-event -> 2025-fall-event.html
/2025-spring-event -> 2025-spring-event.html
/2024-fall-event -> 2024-fall-event.html
/2024-spring-event -> 2024-spring-event.html
/2023-fall-event -> 2023-fall-event.html
/2023-spring-event -> 2023-spring-event.html
/2022-fall-event -> 2022-fall-event.html
/2022-spring-event -> 2022-spring-event.html
/2021-fall-event -> 2021-fall-event.html
/2021-spring-event -> 2021-spring-event.html
/2020-fall-post-event -> 2020-fall-post-event.html



### Membership and Event Register (ignore with new account and event feature)
/membership/signup -> register_form.html
/membership/confirm/<token> -> already_confirmed.html、thanks_confirming.html
/membership/resend-page/<token> -> resend.html
/membership/resend/<token> -> resend.html
/membership/info-form/<token> -> info_form.html
/membership/full-registration/<token> -> complete_registration.html
/membership/update -> enter_form.html
/membership/update/<token> -> update_form.html
/membership/events ->
/membership/events/<event_name> -> event_enter_form.html
/membership/event-registration/<event_name>/<token> -> event_registration.html
/membership/otp -> otp.html

### backend management (ignore with the new Django Admin System)
/admin/ -> admin index page
/admin/login -> admin/login_form.html
/admin/logout -> logout
/admin/register_admin/<token><role> -> admin/register_admin_form.html
/admin/user/ -> Admin List
/admin/user/new_admin -> admin/new_admin_form.html
/admin/edit_form/ -> admin/preview_form.html
/admin/event/ -> event manage page
/admin/contact/ -> admin/contact.html
/admin/manual_email/ -> admin/manual_email.html
/admin/catch_bounces/ -> admin/catch_bounces.html
/admin/documentation/ -> doc
/admin/documentation/documentation -> admin/documentation.html
/admin/prospects/ -> prospects
/admin/prospects/prospects -> admin/prospects.html
