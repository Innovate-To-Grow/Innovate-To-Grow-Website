"""
Rewrite Flask/Jinja2 artefacts in imported legacy Page HTML.

The 48 pages imported by import_legacy_pages still contain raw Jinja2 syntax
from the old Flask site:

  - {% from "includes/..." import ... %}   macro import lines
  - {{ styles() }}                         inline CSS macro call
  - {{ scripts() }}                        inline JS macro call
  - {{ nav() }}                            inline nav macro call
  - {{ footer() }}                         inline footer macro call
  - {{ url_for('static', filename='X') }}  static asset references
  - {{ url_for('home.func_name') }}        internal page links
  - {{ url_for('events.event_redirect') }} membership route links

This command replaces all of the above with correct Django/new-site equivalents
so the pages render properly in the browser.

Usage:
    python manage.py fix_legacy_pages [--dry-run] [--slug legacy/about]

Options:
    --dry-run   Print a diff-style summary without saving to the database.
    --slug      Only process a single page (useful for testing).
"""

import re

from django.core.management.base import BaseCommand

from pages.models import Page

# ---------------------------------------------------------------------------
# Static asset base path — where the copied legacy assets live
# ---------------------------------------------------------------------------
LEGACY_STATIC = "/static/pages/legacy"

# ---------------------------------------------------------------------------
# Flask url_for('home.func') → new site URL
# ---------------------------------------------------------------------------
HOME_URL_MAP: dict[str, str] = {
    "home.mainpage": "/",
    "home.about": "/pages/legacy/about",
    "home.text_toc": "/pages/legacy/privacy",
    "home.engineering_capstone": "/pages/legacy/engineering-capstone",
    "home.about_EngSL": "/pages/legacy/about-engsl",
    "home.software_capstone": "/pages/legacy/software-capstone",
    "home.event": "/pages/legacy/event",
    "home.schedule": "/pages/legacy/schedule",
    "home.projects_teams": "/pages/legacy/projects-teams",
    "home.judges": "/pages/legacy/judges",
    "home.attendees": "/pages/legacy/attendees",
    "home.students": "/pages/legacy/students",
    "home.acknowledgement": "/pages/legacy/acknowledgement",
    "home.past_events": "/pages/legacy/past-events",
    "home.projects": "/pages/legacy/projects",
    "home.past_projects": "/pages/legacy/past-projects",
    "home.current_projects": "/pages/legacy/current-projects",
    "home.project_submission": "/pages/legacy/project-submission",
    "home.sample_proposals": "/pages/legacy/sample-proposals",
    "home.partnership": "/pages/legacy/partnership",
    "home.sponsorship": "/pages/legacy/sponsorship",
    "home.faq": "/pages/legacy/faqs",
    "home.I2G_student_agreement": "/pages/legacy/i2g-student-agreement",
    "home.ferpa": "/pages/legacy/ferpa",
    "home.i2g_students_preparation": "/pages/legacy/i2g-students-preparation",
    "home.video_preparation": "/pages/legacy/video-preparation",
    "home.capstone_purchasing_reimbursement": "/pages/legacy/capstone-purchasing-reimbursement",
    "home.contact_us": "/pages/legacy/contact-us",
    "home.judging": "/pages/legacy/judging",
    "home.template": "/pages/legacy/template",
    "home.template_email_team_students": "/pages/legacy/template-email-team-students",
    "home.I2G_project_sponsor_acknowledgement": "/pages/legacy/i2g-project-sponsor-acknowledgement",
    "home.home_during_event": "/pages/legacy/home-during-event",
    "home.home_post_event": "/pages/legacy/home-post-event",
    "home.fall_event_2025": "/pages/legacy/2025-fall-event",
    "home.spring_event_2025": "/pages/legacy/2025-spring-event",
    "home.fall_event_2024": "/pages/legacy/2024-fall-event",
    "home.spring_event_2024": "/pages/legacy/2024-spring-event",
    "home.fall_event_2023": "/pages/legacy/2023-fall-event",
    "home.spring_event_2023": "/pages/legacy/2023-spring-event",
    "home.fall_event_2022": "/pages/legacy/2022-fall-event",
    "home.spring_event_2022": "/pages/legacy/2022-spring-event",
    "home.fall_event_2021": "/pages/legacy/2021-fall-event",
    "home.spring_event_2021": "/pages/legacy/2021-spring-event",
    "home.fall_event_post_2020": "/pages/legacy/2020-fall-post-event",
    "home.sponsors_2014": "/pages/legacy/2014-sponsors",
    "home.sponsors_2015": "/pages/legacy/2015-sponsors",
    # Membership / external workflows
    "events.event_redirect": "/membership/events",
    "registration.register": "/membership/register",
    "update.enter_email": "/membership/update",
}

# ---------------------------------------------------------------------------
# Expanded macro content (url_for calls already resolved to new paths)
# ---------------------------------------------------------------------------

_STYLES_EXPANDED = (
    '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">\n'
    f'<link type="text/css" rel="stylesheet" href="{LEGACY_STATIC}/css/css-css_xE-rWrJf-fncB6ztZfd2huxqgxu4WO-qwma6Xer30m4.css" media="all">\n'
    f'<link type="text/css" rel="stylesheet" href="{LEGACY_STATIC}/css/css-css_YXH4gT2-px48IhryM34bm9BPKIdC7FXgfCpSr9PWyTE.css" media="all">\n'
    f'<link type="text/css" rel="stylesheet" href="{LEGACY_STATIC}/css/css-css_ikO0Dxm7cLx8sij8aCz93A0aaPm7Vn5LlfEi4H4knHY.css" media="screen">\n'
    f'<link type="text/css" rel="stylesheet" href="{LEGACY_STATIC}/css/css-css_ubzgGJ35RgxN1IJggmIbJzwcE6NtKXa-uNCjJJK6XVo.css" media="all">\n'
    f'<link type="text/css" rel="stylesheet" href="{LEGACY_STATIC}/css/css-css_NYiFQQOJ7xKN-UNsYwHSy9B0FCXYVU-ZlvGwkwzENhA.css" media="all">'
)

_SCRIPTS_EXPANDED = (
    '<script>(function (d) { var s = d.createElement("script"); s.setAttribute("data-account", "6Uvgvyrrph"); '
    's.setAttribute("src", "https://cdn.userway.org/widget.js"); (d.body || d.head).appendChild(s); })(document)</script>\n'
    "<noscript>Please ensure Javascript is enabled for purposes of "
    '<a href="https://userway.org">website accessibility</a></noscript>\n'
    f'<script src="{LEGACY_STATIC}/js/js-siteimprove.js" async></script>\n'
    f'<script type="text/javascript" src="{LEGACY_STATIC}/js/js-js_XexEZhbTmj1BHeajKr2rPfyR8Y68f4rm0Nv3Vj5_dSI.js"></script>\n'
    f'<script type="text/javascript" src="{LEGACY_STATIC}/js/js-js_jcCq6mIiUQO8UVHPQGodwBB20SVk57zQ9OUDx6L6OC0.js"></script>\n'
    f'<script type="text/javascript" src="{LEGACY_STATIC}/js/js-js_lYXBf5jBOEeuCcZ1EEfWM3cnZXJ6-B6AuswWtJ1JGSw.js"></script>\n'
    f'<script type="text/javascript" src="{LEGACY_STATIC}/js/js-js_jWvMRvZ8oKDPkw7PO6dSKi88lBTsNPnOLr3hiyfvSnE.js"></script>\n'
    f'<script type="text/javascript" src="{LEGACY_STATIC}/js/js-js_Btvj6RNWy6mW_Y-FXH9a4UVDI19MXIlXYDvxbme4QeE.js"></script>\n'
    '<script src="https://ajax.googleapis.com/ajax/libs/jquery/3.6.1/jquery.min.js"></script>\n'
    f'<script src="{LEGACY_STATIC}/js/recaptcha-api.js" async defer></script>'
)

# Nav HTML with all url_for calls already resolved (derived from includes/nav.html)
_NAV_EXPANDED = f"""<!-- NAVBAR -->
<div id="header" class="clearfix header" role="banner">
    <div class="container">
        <div class="row-fluid">
            <div class="header-section row-fluid span12">
                <div id="stickyHeader">
                    <div class="site-logo">
                        <a href="https://www.ucmerced.edu" title="Home" rel="home" style="border: none;"> <img
                                src="https://innovatetogrow.ucmerced.edu/sites/all/themes/UCMerced/ucmlogo.png"
                                alt="UC Merced logo" role="presentation"> </a>
                    </div>
                    <style>
                    @media (max-width: 768px) {{
                      .logo-link {{
                        margin-left: -10% !important;
                        margin-right: auto !important;
                        text-align: left !important;
                      }}
                    }}
                    </style>
                    <a href="/"
                       class="logo-link"
                       style="display: block; width: 200px; max-width: 80%; margin-left: 24%; text-align: left;">
                        <img src="{LEGACY_STATIC}/images/I2G-fullname-low.png"
                             alt="I2G Logo"
                             style="width: 100%; height: auto; display: block;">
                    </a>
                    <div class="quick-links" id="quickLinksNavigation">
                        <a href="https://directory.ucmerced.edu/?_gl=1*12bbiew*_ga*MzM3MTQxMzQ2LjE2ODA3MzU0MDM.*_ga_TSE2LSBDQZ*MTY4MDczODY2My4yLjEuMTY4MDczODY2My42MC4wLjA." target="_blank" rel="noopener">Directory</a>
                        <a href="https://admissions.ucmerced.edu/first-year/apply?button" target="_blank" rel="noopener">Apply</a>
                        <a href="http://giving.ucmerced.edu/" target="_blank" rel="noopener">Give</a>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
<div id="siteName">
    <div class="container">
        <div class="row-fluid">
            <div class="name-slogan span12">
                <div id="site-name" class="site-name"><a href="/" title="Home" rel="home">Innovate To Grow</a></div>
            </div>
        </div>
    </div>
</div>
<div id="main-menu" class="clearfix site-main-menu">
    <div class="container">
        <div class="navbar row-fluid">
            <div class="navbar-inner1 span12">
                <button aria-label="Navigation menu" class="btn-navbar collapsed" data-toggle="collapse"
                    data-target=".nav-collapse"> <span class="hide">Navigation menu</span> <span
                        class="icon-bar top-bar"></span> <span class="icon-bar middle-bar"></span> <span
                        class="icon-bar bottom-bar"></span> </button>
                <div class="nav-collapse collapse">
                    <nav id="main-nav" role="navigation">
                        <div class="region region-navigation clearfix">
                            <div id="block-superfish-1" class="clearfix block block-superfish">
                                <h2>Main menu</h2>
                                <div class="content">
                                    <ul id="superfish-1" class="sf-menu main-menu sf-horizontal sf-style-none sf-total-items-10 sf-parent-items-5 sf-single-items-5">
                                        <li style="width: 5%; margin-top: -3px; border-bottom: 0px;"><a href="/"><img src="{LEGACY_STATIC}/images/i2glogo.png"></a></li>
                                        <li id="menu-548-1" class="first odd sf-item-1 sf-depth-1 sf-no-children"><a href="/" title="" class="sf-depth-1  active">Home</a></li>
                                        <li id="menu-538-1" class="middle even sf-item-2 sf-depth-1 sf-total-children-3 sf-parent-children-0 sf-single-children-3 menuparent">
                                            <a href="/pages/legacy/about" class="sf-depth-1  menuparent">About</a>
                                            <ul>
                                                <li id="menu-4471-1" class="first odd sf-item-1 sf-depth-2 sf-no-children"><a href="/pages/legacy/engineering-capstone" title="" class="sf-depth-2 ">Engineering Capstone</a></li>
                                                <li id="menu-544-1" class="middle even sf-item-2 sf-depth-2 sf-no-children"><a href="https://engineeringservicelearning.ucmerced.edu/" title="" class="sf-depth-2 ">Eng. Service Learning</a></li>
                                                <li id="menu-4481-1" class="last odd sf-item-3 sf-depth-2 sf-no-children"><a href="/pages/legacy/software-capstone" title="" class="sf-depth-2 ">Software Eng. Capstone</a></li>
                                            </ul>
                                        </li>
                                        <li id="menu-5291-1" class="middle odd sf-item-3 sf-depth-1 sf-total-children-7 sf-parent-children-0 sf-single-children-7 menuparent">
                                            <a href="/pages/legacy/event" title="" class="sf-depth-1  menuparent">Events</a>
                                            <ul>
                                                <li id="menu-5301-1" class="first odd sf-item-1 sf-depth-2 sf-no-children"><a href="/membership/events" title="" class="sf-depth-2 ">Registration</a></li>
                                                <li id="menu-5301-1" class="first odd sf-item-2 sf-depth-2 sf-no-children"><a href="/pages/legacy/event" title="" class="sf-depth-2 ">Event Info</a></li>
                                                <li id="menu-5371-1" class="middle even sf-item-3 sf-depth-2 sf-no-children"><a href="/pages/legacy/schedule" title="" class="sf-depth-2 ">Schedule</a></li>
                                                <li id="menu-5321-1" class="middle odd sf-item-4 sf-depth-2 sf-no-children"><a href="/pages/legacy/projects-teams" title="" class="sf-depth-2 ">Projects &amp; Teams</a></li>
                                                <li id="menu-5331-1" class="middle even sf-item-5 sf-depth-2 sf-no-children"><a href="/pages/legacy/judges" title="" class="sf-depth-2 ">for Judges</a></li>
                                                <li id="menu-5341-1" class="middle odd sf-item-6 sf-depth-2 sf-no-children"><a href="/pages/legacy/attendees" title="" class="sf-depth-2 ">for Attendees</a></li>
                                                <li id="menu-5351-1" class="middle even sf-item-7 sf-depth-2 sf-no-children"><a href="/pages/legacy/students" title="" class="sf-depth-2 ">for Students</a></li>
                                                <li id="menu-5361-1" class="last odd sf-item-8 sf-depth-2 sf-no-children"><a href="/pages/legacy/acknowledgement" title="" class="sf-depth-2 ">Partners &amp; Sponsors</a></li>
                                                <li id="menu-5361-1" class="last odd sf-item-9 sf-depth-2 sf-no-children"><a href="/pages/legacy/past-events" title="" class="sf-depth-2 ">Past Events</a></li>
                                            </ul>
                                        </li>
                                        <li id="menu-4551-1" class="middle odd sf-item-4 sf-depth-1 sf-total-children-4 sf-parent-children-0 sf-single-children-4 menuparent">
                                            <a href="/pages/legacy/projects" title="" class="sf-depth-1  menuparent">Projects</a>
                                            <ul>
                                                <li id="menu-4691-1" class="first odd sf-item-1 sf-depth-2 sf-no-children"><a href="/pages/legacy/past-projects" title="" class="sf-depth-2 ">Past Projects</a></li>
                                                <li id="menu-4561-1" class="middle even sf-item-2 sf-depth-2 sf-no-children"><a href="/pages/legacy/current-projects" title="" class="sf-depth-2 ">Current Projects</a></li>
                                                <li id="menu-4571-1" class="middle odd sf-item-3 sf-depth-2 sf-no-children"><a href="/pages/legacy/project-submission" title="" class="sf-depth-2 ">Project Submission</a></li>
                                                <li id="menu-4581-1" class="last even sf-item-4 sf-depth-2 sf-no-children"><a href="/pages/legacy/sample-proposals" title="" class="sf-depth-2 ">Sample Project Proposals</a></li>
                                            </ul>
                                        </li>
                                        <li id="menu-833-1" class="middle odd sf-item-5 sf-depth-1 sf-total-children-4 sf-parent-children-0 sf-single-children-4 menuparent">
                                            <a href="/pages/legacy/partnership" class="sf-depth-1  menuparent">Partner with Us</a>
                                            <ul>
                                                <li id="menu-5301-1" class="first odd sf-item-1 sf-depth-2 sf-no-children"><a href="/membership/register" title="" class="sf-depth-2 ">Newsletter</a></li>
                                                <li id="menu-5301-1" class="first odd sf-item-2 sf-depth-2 sf-no-children"><a href="/membership/update" title="" class="sf-depth-2 ">Update I2G Membership</a></li>
                                                <li id="menu-5301-1" class="first odd sf-item-3 sf-depth-2 sf-no-children"><a href="/membership/events" title="" class="sf-depth-2 ">Event Registration</a></li>
                                                <li id="menu-4721-1" class="first odd sf-item-4 sf-depth-2 sf-no-children"><a href="/pages/legacy/project-submission" title="" class="sf-depth-2 ">Propose a project</a></li>
                                                <li id="menu-4711-1" class="middle even sf-item-5 sf-depth-2 sf-no-children"><a href="/pages/legacy/judges" title="" class="sf-depth-2 ">Sign up to Judge</a></li>
                                                <li id="menu-647-1" class="middle odd sf-item-6 sf-depth-2 sf-no-children"><a href="/pages/legacy/sponsorship" title="" class="sf-depth-2 ">Sponsor or donate</a></li>
                                                <li id="menu-2511-1" class="last even sf-item-7 sf-depth-2 sf-no-children"><a href="/pages/legacy/faqs" class="sf-depth-2 ">FAQs</a></li>
                                            </ul>
                                        </li>
                                        <li id="menu-3971-1" class="middle even sf-item-8 sf-depth-1 sf-no-children"><a href="/pages/legacy/project-submission" class="sf-depth-1 ">Submit a Project</a></li>
                                        <li id="menu-4661-1" class="middle odd sf-item-6 sf-depth-1 sf-total-children-5 sf-parent-children-0 sf-single-children-5 menuparent">
                                            <a href="/pages/legacy/students" title="" class="sf-depth-1  menuparent">Students</a>
                                            <ul>
                                                <li id="menu-4671-1" class="first odd sf-item-1 sf-depth-2 sf-no-children"><a href="/pages/legacy/i2g-student-agreement" title="" class="sf-depth-2 ">Student Agreement</a></li>
                                                <li id="menu-5381-1" class="middle even sf-item-2 sf-depth-2 sf-no-children"><a href="/pages/legacy/ferpa" title="" class="sf-depth-2 ">FERPA (Media) Agreement</a></li>
                                                <li id="menu-4801-1" class="middle odd sf-item-3 sf-depth-2 sf-no-children"><a href="/pages/legacy/i2g-students-preparation" title="" class="sf-depth-2 ">Event preparation</a></li>
                                                <li id="menu-4791-1" class="middle even sf-item-4 sf-depth-2 sf-no-children"><a href="/pages/legacy/video-preparation" title="" class="sf-depth-2 ">Video preparation</a></li>
                                                <li id="menu-2651-1" class="last odd sf-item-5 sf-depth-2 sf-no-children"><a href="/pages/legacy/capstone-purchasing-reimbursement" class="sf-depth-2 ">Purchasing | Travel</a></li>
                                            </ul>
                                        </li>
                                    </ul>
                                </div>
                            </div>
                        </div>
                    </nav>
                    <div id="now-date-weather"><span id="today"></span> <span id="weather"></span></div>
                </div>
            </div>
        </div>
    </div>
</div>"""

# Footer HTML with all url_for calls already resolved (derived from includes/footer.html)
_FOOTER_EXPANDED = f"""<style>
  .footer__bg {{ right: 0; bottom: 0; left: 0; background-color: #f2f2f2; overflow-y: hidden; }}
  .content-wrapper {{ margin: 0 auto; max-width: 87.5rem; }}
  .content-margin {{ margin: 0 auto; max-width: 95%; }}
  .parent__content-box--has-flex-col {{ display: flex; flex-direction: column; padding: 1.25em 0; }}
  .child-parent__primary-col {{ display: flex; flex-direction: column; margin: 3.75em 0; }}
  div.child__primary-row-items {{ align-self: center; }}
  div.child__primary-row-items a {{ margin: 0 3.125em; display: inline-block; }}
  div.child__primary-row-items a i {{ font-size: 3.125rem; color: #fafafa; }}
  div.child__primary-row-items a span {{ display: none; }}
  div.child__primary-row-items a:hover {{ opacity: 0.8; }}
  div.child__primary-row-items a:active {{ opacity: 0.95; }}
  .child-parent__secondary-col--has-flex-row {{ display: flex; justify-content: space-between; border-top: 1px ridge rgba(204, 204, 204, 0.4); border-bottom: 1px ridge rgba(204, 204, 204, 0.4); padding: 1.25em 0; }}
  ul.child__primary-row-items {{ display: flex; }}
  ul.child__primary-row-items li:not(:last-child)::after {{ position: absolute; top: 0; right: 12.8%; bottom: 0; font-weight: 900; color: #0f2d52; content: "-"; }}
  ul.child__primary-row-items li {{ position: relative; padding-right: 1.563em; }}
  ul.child__primary-row-items li a {{ font: 1rem "Verdana"; color: #0f2d52; text-decoration: none; }}
  ul.child__primary-row-items li a:hover {{ opacity: 0.8; }}
  ul.child__primary-row-items li a:active {{ opacity: 0.95; }}
  .child__copyright {{ font: 1rem "Verdana"; color: #0f2d52; opacity: 0.75; }}
  @media screen and (max-width: 48em) {{
    .child-parent__primary-col {{ margin: 3.125em 0; }}
    div.child__primary-row-items a {{ margin: 0 clamp(1.563em, 6.9vw, 3.125em); }}
    .child-parent__secondary-col--has-flex-row {{ justify-content: center; border-bottom: unset; padding-bottom: unset; }}
  }}
  @media screen and (max-width: 30em) {{
    div.child__primary-row-items {{ display: flex; flex-direction: column; }}
    div.child__primary-row-items a {{ display: flex; align-items: center; margin: 0 0 0.9375em; text-decoration: none; }}
    div.child__primary-row-items a i {{ margin-right: 0.46875em; font-size: 2rem; }}
    div.child__primary-row-items a span {{ display: inline; font: 1rem "Verdana"; color: #0f2d52; }}
    div.child__primary-row-items a:last-child {{ margin-bottom: 0; }}
    div.child__primary-row-items a:active span {{ text-decoration: underline; text-underline-offset: 0.25em; }}
    .child-parent__secondary-col--has-flex-row {{ flex-direction: column; align-items: center; }}
    .child__copyright {{ margin-top: 0.625em; font-size: 0.906rem; }}
  }}
</style>
<p>&nbsp;</p>
<div class="sb-row" style="padding-top: 0px; text-align: center; justify-content: center; margin-top: 10px;">
  <div class="sb-col hb__buttons-blue"><a class="btn--invert-blue hb__play" href="/pages/legacy/about">About Us</a></div>
  <div class="sb-col hb__buttons-gold"><a class="btn--invert-gold hb__play" href="/pages/legacy/past-projects">Past Projects</a></div>
  <div class="sb-col hb__buttons-blue"><a class="btn--invert-blue hb__play" href="/membership/events">Event Registration</a></div>
  <div class="sb-col hb__buttons-gold"><a class="btn--invert-gold hb__play" href="/pages/legacy/project-submission">Submit a Project</a></div>
  <div class="sb-col hb__buttons-blue"><a class="btn--invert-blue hb__play" href="/membership/register">Signup for News</a></div>
  <div class="sb-col hb__buttons-gold"><a class="btn--invert-gold hb__play" href="/membership/update">Update Membership</a></div>
  <div class="i2gHome">
    <p>&nbsp;</p>
    <p>For any questions or comments, please send an email to: <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a></p>
  </div>
</div>
</div>
<div id="footer" class="clearfix site-footer" role="contentinfo">
  <div class="container">
    <div id="footer-content" class="row-fluid footer-content"></div>
  </div>
  <div class="final-foot">
    <div class="container">
      <div class="footer-links">
        <div class="fColumn">
          <h2>Additional Links</h2>
          <ul>
            <li><a href="https://www.ucmerced.edu" target="_blank" rel="noopener">UC Merced</a></li>
            <li><a href="https://news.ucmerced.edu" target="_blank" rel="noopener">Newsroom</a></li>
            <li><a href="https://www.ucmerced.edu/executive-leadership" target="_blank" rel="noopener">Executive Leadership</a></li>
            <li><a href="https://library.ucmerced.edu" target="_blank" rel="noopener">University Library</a></li>
            <li><a href="https://it.ucmerced.edu" target="_blank" rel="noopener">Office of Information Technology</a></li>
          </ul>
        </div>
        <div class="fColumn">
          <h2>Academics</h2>
          <ul>
            <li><a href="https://engineering.ucmerced.edu" target="_blank" rel="noopener">School of Engineering</a></li>
            <li><a href="https://naturalsciences.ucmerced.edu" target="_blank" rel="noopener">School of Natural Sciences</a></li>
            <li><a href="https://ssha.ucmerced.edu" target="_blank" rel="noopener">School of Social Sciences, Humanities &amp; Arts</a></li>
            <li><a href="https://gallo.ucmerced.edu" target="_blank" rel="noopener">Ernest &amp; Julio Gallo Management Program</a></li>
            <li><a href="https://graduatedivision.ucmerced.edu" target="_blank" rel="noopener">Division of Graduate Education</a></li>
            <li><a href="https://ue.ucmerced.edu" target="_blank" rel="noopener">Division of Undergraduate Education</a></li>
          </ul>
        </div>
        <div class="fColumn">
          <h2>Administration</h2>
          <ul>
            <li><a href="https://chancellor.ucmerced.edu" target="_blank" rel="noopener">Office of the Chancellor</a></li>
            <li><a href="https://provostevc.ucmerced.edu" target="_blank" rel="noopener">Office of Executive Vice Chancellor and Provost</a></li>
            <li><a href="https://diversity.ucmerced.edu" target="_blank" rel="noopener">Equity, Justice and Inclusive Excellence</a></li>
            <li><a href="https://externalrelations.ucmerced.edu" target="_blank" rel="noopener">External Relations</a></li>
            <li><a href="https://dfa.ucmerced.edu" target="_blank" rel="noopener">Finance &amp; Administration</a></li>
            <li><a href="https://popd.ucmerced.edu" target="_blank" rel="noopener">Physical Operations, Planning and Development</a></li>
            <li><a href="https://studentaffairs.ucmerced.edu" target="_blank" rel="noopener">Student Affairs</a></li>
            <li><a href="https://research.ucmerced.edu" target="_blank" rel="noopener">Research and Economic Development</a></li>
          </ul>
        </div>
        <div class="fColumn fAddress">
          <p><strong>University of California, Merced</strong><br>5200 North Lake Rd.<br>Merced, CA 95343<br>Telephone: (209) 228-4400</p>
          <div class="socialIcons">
            <ul class="fa-ul inline">
              <li class="fa-li"><a href="https://www.facebook.com/ucmerced/" target="_blank" rel="noopener" aria-label="Facebook"><i class="fa fa-facebook"></i></a></li>
              <li class="fa-li"><a href="https://twitter.com/ucmerced" target="_blank" rel="noopener" aria-label="Twitter"><i class="fa fa-twitter"></i></a></li>
              <li class="fa-li"><a href="https://www.linkedin.com/company/22066" target="_blank" rel="noopener" aria-label="Linkedin"><i class="fa fa-linkedin"></i></a></li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  </div>
  <div class="copyright">
    <ul>
      <li>© 2023</li>
      <li><a href="https://www.ucmerced.edu/about" rel="noopener">About UC Merced</a></li>
      <li><a href="https://www.ucmerced.edu/maps-and-directions" rel="noopener">Directions</a></li>
      <li><a href="https://directory.ucmerced.edu/">Directory</a></li>
      <li><a href="https://www.ucmerced.edu/privacy-statement" rel="noopener">Privacy/Legal</a></li>
      <li><a href="/pages/legacy/contact-us">Site Feedback</a></li>
      <li><a href="https://regents.universityofcalifornia.edu/" rel="noopener">UC Regents</a></li>
      <li><a href="https://www.ucmerced.edu/Site-List-A-F" rel="noopener">Site List</a></li>
    </ul>
  </div>
</div>"""

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# {% from "includes/..." import ... %} — entire line
_RE_JINJA_IMPORT = re.compile(r'\{%-?\s*from\s+"includes/[^"]+"\s+import\s+\w+\s*-?%\}\n?')

# {{ styles() }} / {{ scripts() }} / {{ nav() }} / {{ footer() }}
_RE_MACRO_STYLES = re.compile(r"\{\{-?\s*styles\(\)\s*-?\}\}")
_RE_MACRO_SCRIPTS = re.compile(r"\{\{-?\s*scripts\(\)\s*-?\}\}")
_RE_MACRO_NAV = re.compile(r"\{\{-?\s*nav\(\)\s*-?\}\}")
_RE_MACRO_FOOTER = re.compile(r"\{\{-?\s*footer\(\)\s*-?\}\}")

# {{ url_for('static', filename='path/to/file') }}  (spaces around = optional)
_RE_STATIC_URL = re.compile(
    r"""\{\{-?\s*url_for\(\s*['"]static['"]\s*,\s*filename\s*=\s*['"]([^'"]+)['"]\s*\)\s*-?\}\}"""
)

# {{ url_for('blueprint.view_name') }}  or  {{ url_for('blueprint.view_name', ...) }}
# We capture 'blueprint.view_name' and ignore any extra kwargs.
# Note: digits are allowed in view names (e.g. fall_event_2025, I2G_student_agreement).
_RE_ROUTE_URL = re.compile(
    r"""\{\{-?\s*url_for\(\s*['"]([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)['"]\s*(?:,\s*[^)]+)?\)\s*-?\}\}"""
)

# Any remaining {{ ... }} or {% ... %} — for reporting
_RE_JINJA_REMAINING = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.DOTALL)


# ---------------------------------------------------------------------------
# Core rewrite logic
# ---------------------------------------------------------------------------

def _rewrite_html(html: str) -> tuple[str, list[str]]:
    """
    Apply all substitutions to a page's HTML.

    Returns (rewritten_html, warnings) where warnings lists any Jinja2
    expressions that could not be resolved.
    """
    # 1. Strip Jinja2 macro import lines
    html = _RE_JINJA_IMPORT.sub("", html)

    # 2. Expand macro calls
    html = _RE_MACRO_STYLES.sub(_STYLES_EXPANDED, html)
    html = _RE_MACRO_SCRIPTS.sub(_SCRIPTS_EXPANDED, html)
    html = _RE_MACRO_NAV.sub(_NAV_EXPANDED, html)
    html = _RE_MACRO_FOOTER.sub(_FOOTER_EXPANDED, html)

    # 3. Rewrite {{ url_for('static', filename='X') }} → /static/pages/legacy/X
    def _replace_static(m: re.Match) -> str:
        return f"{LEGACY_STATIC}/{m.group(1)}"

    html = _RE_STATIC_URL.sub(_replace_static, html)

    # 4. Rewrite {{ url_for('blueprint.view') }} → mapped URL
    def _replace_route(m: re.Match) -> str:
        key = m.group(1)
        if key in HOME_URL_MAP:
            return HOME_URL_MAP[key]
        # Unknown route — leave a placeholder comment so it's findable
        return f"<!-- UNRESOLVED: url_for('{key}') -->#"

    html = _RE_ROUTE_URL.sub(_replace_route, html)

    # 5. Collect any remaining Jinja2 expressions for reporting
    remaining = _RE_JINJA_REMAINING.findall(html)
    warnings = [r.strip() for r in remaining]

    return html, warnings


# ---------------------------------------------------------------------------
# Management command
# ---------------------------------------------------------------------------

class Command(BaseCommand):
    help = "Rewrite Flask/Jinja2 artefacts in imported legacy Page HTML."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Show what would change without writing to the database.",
        )
        parser.add_argument(
            "--slug",
            default=None,
            help="Only process a single page by slug (e.g. legacy/about).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        target_slug = options["slug"]

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry-run mode — no database writes.\n"))

        qs = Page.objects.filter(slug__startswith="legacy/")
        if target_slug:
            qs = qs.filter(slug=target_slug)

        if not qs.exists():
            self.stdout.write(self.style.WARNING("No matching pages found."))
            return

        processed = changed = skipped = 0
        all_warnings: dict[str, list[str]] = {}

        for page in qs.order_by("slug"):
            processed += 1
            new_html, warnings = _rewrite_html(page.html)

            if new_html == page.html:
                self.stdout.write(f"  UNCHANGED  {page.slug}")
                skipped += 1
                continue

            # Count substitution delta as a rough diff metric
            old_len = len(page.html)
            new_len = len(new_html)
            delta = new_len - old_len

            if dry_run:
                self.stdout.write(
                    f"  WOULD UPDATE  {page.slug}  "
                    f"({old_len} -> {new_len} chars, {delta:+d})"
                )
            else:
                page.html = new_html
                page.save(update_fields=["html", "updated_at"])
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  UPDATED  {page.slug}  ({old_len} -> {new_len} chars, {delta:+d})"
                    )
                )
            changed += 1

            if warnings:
                all_warnings[page.slug] = warnings

        self.stdout.write("")
        action = "would update" if dry_run else "updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. processed={processed}  {action}={changed}  unchanged={skipped}"
            )
        )

        if all_warnings:
            self.stdout.write("")
            self.stdout.write(
                self.style.WARNING(
                    f"WARNING: {len(all_warnings)} page(s) still contain unresolved Jinja2 expressions:"
                )
            )
            for slug, exprs in all_warnings.items():
                self.stdout.write(f"  {slug}:")
                for expr in exprs[:5]:  # cap at 5 per page to avoid flooding output
                    self.stdout.write(f"    {expr!r}")
                if len(exprs) > 5:
                    self.stdout.write(f"    ... and {len(exprs) - 5} more")
