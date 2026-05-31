# Legacy Event Pages CMS HTML

This document contains CMS page fields and copy-paste HTML for migrating the legacy Innovate to Grow event pages into CMS-managed pages. It intentionally reuses active CMS stylesheet classes from the local database and avoids inline CSS, scripts, Bootstrap layout classes, and DataTables-only behavior.

## Shared CSS/Class Rules

- Use `page_css_class = event-page` on every CMS page.
- Use `Rich Text` blocks for static HTML. The frontend wraps them in `.cms-rich-text`, so base typography and table styles come from the existing CMS styles.
- Use `Embed` blocks for YouTube videos instead of hand-written iframe HTML.
- Use `.ea-*`, `.event-btn-*`, `.schedule-page-agenda-*`, and `.cms-table-block-*` classes already present in active CMS stylesheets.
- Do not paste `<style>`, `<script>`, `style="..."`, `row-fluid`, `span*`, `i2gTable`, `table__wrapper`, `display`, `iframe-container`, or `responsive-iframe`.
- Some legacy schedule cells were filled by JavaScript. The static CMS version keeps available table content and links to the existing interactive `/events/YYYY-season` archive for searchable schedules/projects.

## Past Events Link List Update

Update the `/past-events` CMS page event links to point to the new CMS paths.

```html
<ul class="past-events-page-list">
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2024-fall">Fall 2024 Event Page</a></li>
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2024-spring">Spring 2024 Event Page</a></li>
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2023-fall">Fall 2023 Event Page</a></li>
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2023-spring">Spring 2023 Event Page</a></li>
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2022-fall">Fall 2022 Event Page</a></li>
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2022-spring">Spring 2022 Event Page</a></li>
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2021-fall">Fall 2021 Event Page</a></li>
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2021-spring">Spring 2021 Event Page</a></li>
<li class="past-events-page-list-item"><a class="past-events-page-link" href="/event-pages/2020-fall">Fall 2020 Event Page</a></li>
</ul>
```

## Fall 2024 Event Page

### CMS Page Fields

- `slug`: `event-page-2024-fall`
- `route`: `/event-pages/2024-fall`
- `title`: `Fall 2024 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Fall 2024 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Fall 2024 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2024-fall">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Embed - Legacy Video

- `src`: `https://www.youtube.com/embed/0KdRs3Dz9G8`
- `title`: `Fall 2024 Event Page video`
- `aspect_ratio`: `16:9`
- `allowfullscreen`: checked

### Block 3: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<br/><h4>The Innovate to Grow program</h4><div>

<img alt="logo, icon" src="https://i2g.ucmerced.edu/static/images/i2glogo.png"/>

<p class="ea-text">
                                                    Innovate to Grow (I2G) is a unique &ldquo;experiential learning&rdquo; program
                                                    that engages
                                                    external partner organizations with teams of students who design
                                                    systems to solve real-world
                                                    problems. The Innovate to Grow program encompasses the following
                                                    experiential learning classes:
                                                    Engineering
                                                        Capstone,
                                                    Engineering Service
                                                        Learning, and
                                                    Software
                                                        Engineering Capstone.
                                                </p>
</div><div><span><strong><span>Winners!&nbsp; Innovate to Grow</span></strong></span>
</div><div><strong>Lakireddy
                                        Engineering Award: CAP-204: Tater Techies</strong></div><div><strong>Lakireddy
                                        Software Award: CSE-314: The Curators</strong></div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;</th>
<th scope="col">
                                                        Track 1
                                                    </th>
<th scope="col">
                                                        Track 2
                                                    </th>
<th scope="col">
                                                        Track 3
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Civil &amp;
                                        Environmental</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 4
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 5
                                                    </th>
<th scope="col">
                                                        Track 6
                                                    </th>
<th scope="col">
                                                        Track 7
                                                    </th>
</tr>
</thead>
<tbody>
<th scope="row">&nbsp;
                                                </th>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
<div><span><strong><span>Mark your calendar!&nbsp; Spring 2025 I2G: Thursday May 15, 2025</span></strong></span>
</div>
</section><h4>Message from the Dean</h4><p class="ea-text">Welcome and participation instructions,
                                                    Mark
                                                    Matsumoto, Dean,
                                                    School of Engineering, University of California, Merced.</p><h4>I2G Information:</h4><a class="event-btn event-btn-blue" href="/events/2024-fall">Event</a><a class="event-btn event-btn-gold" href="/events/2024-fall">Schedule</a><a class="event-btn event-btn-blue" href="/events/2024-fall">Projects &amp;
                                                    Teams</a><a class="event-btn event-btn-gold" href="/attendees">For Attendees</a><a class="event-btn event-btn-blue" href="/judges">For
                                                    Judges</a><a class="event-btn event-btn-gold" href="/students">For
                                                    Students</a><a class="event-btn event-btn-blue" href="/acknowledgement">Our Partners &amp;
                                                    Sponsors</a><div>
<h2 class="ea-section-title">EXPO: POSTERS AND DEMOS</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        Gym&nbsp; &nbsp; (only, NO Zoom)
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">9:00
                                                    </th>
<td>
<p>
                                                            Registration and Coffee</p>
</td>
</tr>
<tr>
<th scope="row">10:00
                                                    </th>
<td>
<p>
                                                            Demos and Posters - Lunch Boxes</p>
</td>
</tr>
<tr>
<th scope="row">
                                                        12:00
                                                    </th>
<td>
<p>
                                                            Networking - Transition to Presentations</p>
</td>
</tr>
</tbody>
</table></div>
</section><div>
<h2 class="ea-section-title">PRESENTATIONS</h2>
</div><div>
<h2 class="ea-section-title">AWARDS &amp; RECEPTION</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        Conference Center
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">4:30
                                                    </th>
<td>
<p>
                                                            Award Ceremony</p>
</td>
</tr>
<tr>
<th scope="row">5:00
                                                    </th>
<td>
<p>
                                                            Reception</p>
</td>
</tr>
<tr></tr>
</tbody>
</table></div>
</section><div id="projects">
<div class="cms-table-block-wrap"><table class="cms-table-block-table" id="example">
<thead>
<tr>
<th>Track</th>
<th>Year-Semester</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
<th>Industry</th>
<th>More Info</th>
<th>&nbsp;</th>
<th>&nbsp;</th>
</tr>
</thead>
</table></div>
</div>
```

### Classes Used

`cms-table-block-table`, `cms-table-block-wrap`, `ea-back-link`, `ea-header`, `ea-section-title`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`

## Spring 2024 Event Page

### CMS Page Fields

- `slug`: `event-page-2024-spring`
- `route`: `/event-pages/2024-spring`
- `title`: `Spring 2024 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Spring 2024 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Spring 2024 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2024-spring">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Embed - Legacy Video

- `src`: `https://www.youtube.com/embed/0KdRs3Dz9G8`
- `title`: `Spring 2024 Event Page video`
- `aspect_ratio`: `16:9`
- `allowfullscreen`: checked

### Block 3: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<br/><h4>The Innovate to Grow program</h4><div>

<img alt="logo, icon" src="https://i2g.ucmerced.edu/static/images/i2glogo.png"/>

<p class="ea-text">
                                                    Innovate to Grow (I2G) is a unique &ldquo;experiential learning&rdquo; program
                                                    that engages
                                                    external partner organizations with teams of students who design
                                                    systems to solve real-world
                                                    problems. The Innovate to Grow program encompasses the following
                                                    experiential learning classes:
                                                    Engineering
                                                        Capstone,
                                                    Engineering Service
                                                        Learning, and
                                                    Software
                                                        Engineering Capstone.
                                                </p>
</div><div><span><strong><span>Winners!&nbsp; Innovate to Grow</span></strong></span>
</div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;</th>
<th scope="col">
                                                        Track 1
                                                    </th>
<th scope="col">
                                                        Track 2
                                                    </th>
<th scope="col">
                                                        Track 3
                                                    </th>
<th scope="col">
                                                        Track 4
                                                    </th>
<th scope="col">
                                                        Track 5
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering Capstone
                                    (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                    &nbsp;
                                                </th>
<th scope="col">Track
                                                    6
                                                </th>
<th scope="col">Track
                                                    7
                                                </th>
<th scope="col">Track
                                                    8
                                                </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                </th>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                </th>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
</tr>
</tbody>
</table></div>
<div><span><strong><span>Mark your calendar!&nbsp; Fall 2024 I2G: Thursday, December 19, 2024</span></strong></span>
</div>
</section>
```

### Classes Used

`ea-back-link`, `ea-header`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`

## Fall 2023 Event Page

### CMS Page Fields

- `slug`: `event-page-2023-fall`
- `route`: `/event-pages/2023-fall`
- `title`: `Fall 2023 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Fall 2023 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Fall 2023 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2023-fall">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Embed - Legacy Video

- `src`: `https://www.youtube.com/embed/0KdRs3Dz9G8`
- `title`: `Fall 2023 Event Page video`
- `aspect_ratio`: `16:9`
- `allowfullscreen`: checked

### Block 3: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<br/><h4>The Innovate to Grow program</h4><p class="ea-text">Innovate to Grow (I2G) is a unique &ldquo;experiential learning&rdquo; program that
                                                engages
                                                external partner
                                                organizations with teams of students who design systems to solve
                                                real-world
                                                problems. The Innovate to
                                                Grow program encompasses the following experiential learning classes: Engineering
                                                    Capstone, Engineering
                                                    Service Learning, and Software
                                                    Engineering
                                                    Capstone.</p><div><span><strong><span>Winners!&nbsp; Innovate to Grow</span></strong></span>
</div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;</th>
<th scope="col">
                                                        Track 1
                                                    </th>
<th scope="col">
                                                        Track 2
                                                    </th>
<th scope="col">
                                                        Track 3
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Civil &amp;
                                        Environmental</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 4
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 5
                                                    </th>
<th scope="col">
                                                        Track 6
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><h4>Message from the Dean</h4><p class="ea-text">Welcome and participation instructions,
                                                    Mark
                                                    Matsumoto, Dean,
                                                    School of Engineering, University of California, Merced.</p><h4>I2G Information:</h4><a class="event-btn event-btn-blue" href="/events/2023-fall">Event</a><a class="event-btn event-btn-gold" href="/events/2023-fall">Schedule</a><a class="event-btn event-btn-blue" href="/events/2023-fall">Projects &amp;
                                                    Teams</a><a class="event-btn event-btn-gold" href="/attendees">For Attendees</a><a class="event-btn event-btn-blue" href="/judges">For
                                                    Judges</a><a class="event-btn event-btn-gold" href="/students">For
                                                    Students</a><a class="event-btn event-btn-blue" href="/acknowledgement">Our Partners &amp;
                                                    Sponsors</a><div>
<h2 class="ea-section-title">EXPO: POSTERS AND DEMOS</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        Gym&nbsp; &nbsp; (only, NO Zoom)
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">10:30
                                                    </th>
<td>
<p>
                                                            Registration and Coffee</p>
</td>
</tr>
<tr>
<th scope="row">11:30
                                                    </th>
<td>
<p>
                                                            Demos and Posters - Lunch Boxes</p>
</td>
</tr>
<tr>
<th scope="row">
                                                        2:00
                                                    </th>
<td>
<p>
                                                            Networking - Transition to Presentations</p>
</td>
</tr>
</tbody>
</table></div>
</section><div>
<h2 class="ea-section-title">PRESENTATIONS</h2>
</div><div>
<h2 class="ea-section-title">AWARDS &amp; RECEPTION</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        Conference Center
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">5:45
                                                    </th>
<td>
<p>
                                                            Award Ceremony</p>
</td>
</tr>
<tr>
<th scope="row">6:00
                                                    </th>
<td>
<p>
                                                            Reception</p>
</td>
</tr>
<tr></tr>
</tbody>
</table></div>
</section><div id="projects">
<div class="cms-table-block-wrap"><table class="cms-table-block-table" id="example">
<thead>
<tr>
<th>Track</th>
<th>Year-Semester</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
<th>Industry</th>
<th>More Info</th>
<th>&nbsp;</th>
<th>&nbsp;</th>
</tr>
</thead>
</table></div>
</div>
```

### Classes Used

`cms-table-block-table`, `cms-table-block-wrap`, `ea-back-link`, `ea-header`, `ea-section-title`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`

## Spring 2023 Event Page

### CMS Page Fields

- `slug`: `event-page-2023-spring`
- `route`: `/event-pages/2023-spring`
- `title`: `Spring 2023 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Spring 2023 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Spring 2023 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2023-spring">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<div><span><strong><span>Winners!&nbsp; Innovate to Grow - Spring 2023</span></strong></span>
</div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;</th>
<th scope="col">
                                                        Track 1
                                                    </th>
<th scope="col">
                                                        Track 2
                                                    </th>
<th scope="col">
                                                        Track 3
                                                    </th>
<th scope="col">
                                                        Track 4
                                                    </th>
<th scope="col">
                                                        Track 5
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Civil &amp;
                                        Environmental</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 6
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 7
                                                    </th>
<th scope="col">
                                                        Track 8
                                                    </th>
<th scope="col">
                                                        Track 9
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><h4><strong>Thursday</strong>, May&nbsp;11, 2023&nbsp;- 10:30&nbsp;- 7:00</h4><ul>
<li>10:30&nbsp;&nbsp;<b>Registration </b>+ Coffee&nbsp;- Gym</li>
<li>11:30&nbsp;&nbsp;<b>Expo</b>&nbsp;(Posters - Demos - Lunch) - Gym (no Zoom)
                                        </li>
<li>2:00&nbsp;&nbsp;<b>Presentations</b>&nbsp;- COB bldg. + Zoom (see schedule
                                            for Rooms)
                                        </li>
<li>5:45&nbsp;&nbsp;<b>Awards Ceremony</b>&nbsp;- Gym</li>
<li>6:00&nbsp;&nbsp;<b>Reception</b>&nbsp;- Gym</li>
</ul><a class="event-btn event-btn-gold" href="/event-registration">Register NOW !</a><h4>Preparing for the Event</h4><ul>
<li><strong><a href="/event-registration">Register
                                            ASAP</a></strong>&nbsp; to attend <strong>in person</strong> or <strong>on
                                            zoom</strong>!
                                        </li>
<li>To attend on Zoom, ensure&nbsp;<strong>your account</strong> displays your
                                            <strong>Full Name</strong>.
                                        </li>
<li>Review schedule,&nbsp;projects, and teams (below):&nbsp;check for updates!
                                        </li>
<li>You may <strong>click on a team</strong> (e.g. CSE-314) to open that
                                            <strong>team info</strong>.
                                        </li>
<li>Then, you may click the <strong>open/close icon</strong>&nbsp;to view
                                            <strong>project details</strong>.
                                        </li>
</ul><a class="event-btn event-btn-gold" href="/attendees">For
                                            Attendees</a><a class="event-btn event-btn-blue" href="/judges">For
                                            Judges</a><h4>Attend in Person:&nbsp; (<strong><u><a href="https://drive.google.com/file/d/1n570qiaC47TG62eVymd7wcS5VdY9O5OL/view?usp=share_link" rel="noopener noreferrer" target="_blank">EVENT MAP</a></u></strong>)</h4><ul>
<li><strong>Park </strong>in the reserved area in the Bellevue&nbsp;Lot (Gold
                                            section - follow signs).
                                        </li>
<li><strong>Walk or shuttle</strong> to the Gym.</li>
<li>Pick up your <strong>badge </strong>at the Registration desk.</li>
<li>Registration and <strong>coffee </strong>start at 10:30.</li>
<li><strong>Expo </strong>doors open at 11:15&nbsp;for student posters/demos.
                                        </li>
<li><strong>Lunch </strong>is served in boxes at the Gym.</li>
<li><strong>Presentations </strong>start promptly at 2:00&nbsp;at COB building!&nbsp;
                                        </li>
<li>Search the room of your desired <strong>track&nbsp;</strong>(see the
                                            schedule below).
                                        </li>
<li>You may also attend the Award Ceremony and the Reception.</li>
</ul><h4>Attend on Zoom:</h4><ul>
<li>You may <strong>only</strong>&nbsp;view
                                            the&nbsp;<strong>Presentations</strong>, not the Expo and Awards.
                                        </li>
<li><strong>Each Track</strong> is held in a <strong>separate Zoom Room</strong>.
                                        </li>
<li>Plan to click the <a href="/">I2G Home Page</a>
<strong> by 1:50&nbsp;</strong>to find and join a track!
                                        </li>
<li>Access to <strong>Zoom rooms </strong> will appear in the Schedule below and
                                            in the <a href="/">I2G Home Page</a><strong>&nbsp;</strong>on
                                            the event day<strong>&nbsp;after&nbsp;1:50!</strong></li>
<li>Sign in <strong>your Zoom account,&nbsp;</strong>make sure your <strong>&ldquo;Display
                                            Name&rdquo;</strong> is your Full Name.
                                        </li>
<li><strong>Click the button&nbsp;</strong>of the desired&nbsp;<strong>Track #&nbsp;</strong>(passcode
                                            is:&nbsp;&nbsp;I2G).
                                        </li>
<li>Presentations will <strong>start promptly at 2:00</strong>!&nbsp;&nbsp;</li>
<li>You may change Zoom Room to change track!</li>
</ul><div>
<h2 class="ea-section-title">EXPO: POSTERS AND DEMOS</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        Gym&nbsp; &nbsp; (only, NO Zoom)
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">10:30
                                                    </th>
<td>
<p>
                                                            Registration and Coffee</p>
</td>
</tr>
<tr>
<th scope="row">11:30
                                                    </th>
<td>
<p>
                                                            Demos and Posters - Lunch Boxes</p>
</td>
</tr>
<tr>
<th scope="row">
                                                        2:00
                                                    </th>
<td>
<p>
                                                            Networking - Transition to Presentations</p>
</td>
</tr>
</tbody>
</table></div>
</section><div>
<h2 class="ea-section-title">PRESENTATIONS</h2>
</div><div>
<h2 class="ea-section-title">AWARDS &amp; RECEPTION</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        Conference Center
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">5:45
                                                    </th>
<td>
<p>
                                                            Award Ceremony</p>
</td>
</tr>
<tr>
<th scope="row">6:00
                                                    </th>
<td>
<p>
                                                            Reception</p>
</td>
</tr>
<tr></tr>
</tbody>
</table></div>
</section><div id="projects">
<div class="cms-table-block-wrap"><table class="cms-table-block-table" id="example">
<thead>
<tr>
<th>Track</th>
<th>Year-Semester</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
<th>Industry</th>
<th>More Info</th>
<th>&nbsp;</th>
<th>&nbsp;</th>
</tr>
</thead>
</table></div>
</div>
```

### Classes Used

`cms-table-block-table`, `cms-table-block-wrap`, `ea-back-link`, `ea-header`, `ea-section-title`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`

## Fall 2022 Event Page

### CMS Page Fields

- `slug`: `event-page-2022-fall`
- `route`: `/event-pages/2022-fall`
- `title`: `Fall 2022 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Fall 2022 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Fall 2022 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2022-fall">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<div><span><strong><span>Winners!&nbsp; Innovate to Grow - Fall 2022</span></strong></span>
</div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;</th>
<th scope="col">
                                                        Track 1
                                                    </th>
<th scope="col">
                                                        Track 2
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Civil &amp;
                                        Environmental</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 3
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 4
                                                    </th>
<th scope="col">
                                                        Track 5
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><h4>Friday, December 16, 2022 -&nbsp;9:30AM - 5:00PM</h4><ul>
<li>9:30&nbsp;&nbsp;<b>Registration </b>+ Coffee&nbsp;- Gym</li>
<li>10:00&nbsp;&nbsp;<b>Expo</b>&nbsp;(Posters - Demos) - Gym</li>
<li>12:30&nbsp;&nbsp;<b>Presentations</b>&nbsp;- COB bldg. + Zoom (see schedule
                                            for Rooms)
                                        </li>
<li>15:45&nbsp;&nbsp;<b>Awards Ceremony</b>&nbsp;- Conference Center</li>
<li>16:30&nbsp;&nbsp;<b>Reception</b>&nbsp;- Conference Center</li>
</ul><a class="event-btn event-btn-gold" href="https://i2g-fall-2022.eventbrite.com/" rel="noopener noreferrer" target="_blank">Register NOW !</a><h4>Preparing for the Event</h4><ul>
<li><strong><a href="https://i2g-fall-2022.eventbrite.com/" rel="noopener noreferrer" target="_blank">Register
                                            ASAP</a></strong>&nbsp; to attend <strong>in person</strong> or <strong>on
                                            zoom</strong>!
                                        </li>
<li>To attend on Zoom, ensure&nbsp;<strong>your account</strong> displays your
                                            <strong>Full Name</strong>.
                                        </li>
<li>Review schedule,&nbsp;projects, and teams (below):&nbsp;check for updates!
                                        </li>
<li>You may <strong>click on a team</strong> (e.g. CSE-314) to open that
                                            <strong>team info</strong>.
                                        </li>
<li>Then, you may click the <strong>open/close icon</strong>&nbsp;to view
                                            <strong>project details</strong>.
                                        </li>
</ul><a class="event-btn event-btn-gold" href="/attendees">For
                                            Attendees</a><a class="event-btn event-btn-blue" href="/judges">For
                                            Judges</a><h4>Attend in Person:&nbsp; (<strong><u><a href="https://ucmerced.box.com/s/kmatn6yaxf02hxoz3hy6nm5c4elagdnh" rel="noopener noreferrer" target="_blank">EVENT MAP</a></u></strong>)</h4><ul>
<li><strong>Park </strong>in the reserved area in the Bellevue&nbsp;Lot (Gold
                                            section - follow signs).
                                        </li>
<li><strong>Walk or shuttle</strong> to the Gym.</li>
<li>Pick up your <strong>badge </strong>at the Registration desk.</li>
<li>Registration and <strong>coffee </strong>start at 9:30.</li>
<li><strong>Expo </strong>doors open at 10:00 for student posters/demos.</li>
<li><strong>Lunch </strong>is served in boxes at the Gym.</li>
<li><strong>Presentations </strong>start promptly at 12:30 at COB building!&nbsp;
                                        </li>
<li>Search the room of your desired <strong>track&nbsp;</strong>(see the
                                            schedule below).
                                        </li>
<li>You may also attend the Award Ceremony and the Reception.</li>
</ul><h4>Attend on Zoom:</h4><ul>
<li>You may <strong>only</strong>&nbsp;view
                                            the&nbsp;<strong>Presentations</strong>, not the Expo and Awards.
                                        </li>
<li><strong>Each Track</strong> is held in a <strong>separate Zoom Room</strong>.
                                        </li>
<li>Plan to click the <a href="/">I2G Home Page</a>
<strong> by 12:20&nbsp;</strong>to find and join a track!
                                        </li>
<li>Access to <strong>Zoom rooms </strong> will appear in the Schedule below and
                                            in the <a href="/">I2G Home Page</a><strong>&nbsp;</strong>on
                                            the event day<strong>&nbsp;after&nbsp;12:20!</strong></li>
<li>Sign in <strong>your Zoom account,&nbsp;</strong>make sure your <strong>&ldquo;Display
                                            Name&rdquo;</strong> is your Full Name.
                                        </li>
<li><strong>Click the button&nbsp;</strong>of the desired&nbsp;<strong>Track #&nbsp;</strong>(passcode
                                            is:&nbsp;&nbsp;I2G).
                                        </li>
<li>Presentations will <strong>start promptly at 12:30</strong>!&nbsp;&nbsp;
                                        </li>
<li>You may change Zoom Room to change track!</li>
</ul><div>
<h2 class="ea-section-title">EXPO: POSTERS AND DEMOS</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        Gym&nbsp; &nbsp; (only, NO Zoom)
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">9:30
                                                    </th>
<td>
<p>
                                                            Registration and Coffee</p>
</td>
</tr>
<tr>
<th scope="row">10:00
                                                    </th>
<td>
<p>
                                                            Demos and Posters - Lunch Boxes</p>
</td>
</tr>
<tr>
<th scope="row">
                                                        12:00
                                                    </th>
<td>
<p>
                                                            Networking - Transition to Presentations</p>
</td>
</tr>
</tbody>
</table></div>
</section><div>
<h2 class="ea-section-title">PRESENTATIONS</h2>
</div><div>
<h2 class="ea-section-title">AWARDS &amp; RECEPTION</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        Conference Center
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">3:45
                                                    </th>
<td>
<p>
                                                            Award Ceremony</p>
</td>
</tr>
<tr>
<th scope="row">4:30
                                                    </th>
<td>
<p>
                                                            Reception</p>
</td>
</tr>
<tr></tr>
</tbody>
</table></div>
</section><div id="projects">
<div class="cms-table-block-wrap"><table class="cms-table-block-table" id="example">
<thead>
<tr>
<th>Track</th>
<th>Year-Semester</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
<th>Industry</th>
<th>More Info</th>
<th>&nbsp;</th>
<th>&nbsp;</th>
</tr>
</thead>
</table></div>
</div>
```

### Classes Used

`cms-table-block-table`, `cms-table-block-wrap`, `ea-back-link`, `ea-header`, `ea-section-title`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`

## Spring 2022 Event Page

### CMS Page Fields

- `slug`: `event-page-2022-spring`
- `route`: `/event-pages/2022-spring`
- `title`: `Spring 2022 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Spring 2022 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Spring 2022 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2022-spring">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<div><span><strong><span>Winners!&nbsp; Innovate to Grow - Spring
                                                        2022</span></strong></span></div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;</th>
<th scope="col">Track
                                                        1
                                                    </th>
<th scope="col">Track
                                                        2
                                                    </th>
<th scope="col">Track
                                                        3
                                                    </th>
<th scope="col">Track
                                                        4
                                                    </th>
<th scope="col">Track
                                                        5
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th>&nbsp;</th>
<td>
<p>AgTech
                                                        </p>
</td>
<td>
<p>Process
                                                        </p>
</td>
<td>
<p>
<b>Safety</b>
</p>
</td>
<td>
<p>
<b>System</b>
</p>
</td>
<td>
<p>
<b>Waste</b>
</p>
</td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
<td><b>&nbsp;</b>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>CEE + EngSL</strong>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;
                                                    </th>
<th scope="col">
                                                        Track 6
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td>
<p><b>Environment (CEE)</b></p>
</td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b>
</td>
</tr>
</tbody>
</table></div>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;
                                                    </th>
<th scope="col">
                                                        Track 7
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td>
<p><b>Service Learning</b></p>
</td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">Track
                                                        8
                                                    </th>
<th scope="col">Track
                                                        9
                                                    </th>
<th scope="col">Track
                                                        10
                                                    </th>
<th scope="col">Track
                                                        11
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td>
<p><b>Code</b></p>
</td>
<td>
<p><b>Computer</b></p>
</td>
<td>
<p><b>Data</b></p>
</td>
<td>
<p><b>User</b></p>
</td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
<td><b>&nbsp;</b></td>
</tr>
</tbody>
</table></div>
</section><h4>Friday, May 13, 2022 -&nbsp;9:30AM - 5:00PM</h4><ul>
<li>9:30&nbsp;&nbsp;<b>Registration </b>+ Coffee&nbsp;- Gym</li>
<li>10:00&nbsp;&nbsp;<b>Expo</b>&nbsp;(Posters - Demos) - Gym</li>
<li>12:30&nbsp;&nbsp;<b>Presentations</b>&nbsp;- Campus and&nbsp;Zoom (see
                                            schedule for Rooms)
                                        </li>
<li>15:45&nbsp;&nbsp;<b>Awards Ceremony</b>&nbsp;- Gym</li>
<li>16:30&nbsp;&nbsp;<b>Reception</b>&nbsp;- Gym</li>
</ul><a class="event-btn event-btn-gold" href="https://i2g-spring-2022.eventbrite.com/" rel="noopener noreferrer" target="_blank">Register NOW</a>&nbsp;!
                                        <h4>Preparing for the Event</h4><ul>
<li><strong><a href="https://i2g-spring-2022.eventbrite.com/" rel="noopener noreferrer" target="_blank">Register ASAP</a></strong>&nbsp; to attend
                                            <strong>in person</strong> or <strong>on zoom</strong>!
                                        </li>
<li>To attend on Zoom, ensure&nbsp;<strong>your account</strong> displays
                                            your <strong>Full Name</strong>.
                                        </li>
<li>Review schedule,&nbsp;projects, and teams (below):&nbsp;check for
                                            updates!
                                        </li>
<li>You may <strong>click on a team</strong> (e.g. CSE-314) to open that
                                            <strong>team info</strong>.
                                        </li>
<li>Then, you may click the <strong>open/close icon</strong>&nbsp;to view
                                            <strong>project details</strong>.
                                        </li>
</ul><a class="event-btn event-btn-gold" href="/attendees">For
                                            Attendees</a><a class="event-btn event-btn-blue" href="/judges">For
                                            Judges</a><h4>Attend in Person:&nbsp; (<strong><u><a href="https://ucmerced.box.com/s/yiadwxs6l0ipz9umd8hpe39oexfmn2av" rel="noopener noreferrer" target="_blank">EVENT MAP</a></u></strong>)</h4><ul>
<li><strong>Park </strong>in the reserved area in the North Bowl
                                            Lot&nbsp;(follow signs).
                                        </li>
<li><strong>Walk or shuttle</strong> to the Gym.</li>
<li>Pick up your <strong>badge </strong>at the Registration desk.</li>
<li>Registration and <strong>coffee </strong>start at 9:30.</li>
<li><strong>Expo </strong>doors open at 10:00 for student posters/demos.
                                        </li>
<li><strong>Lunch </strong>is served in boxes at the Gym.</li>
<li><strong>Presentations </strong>start promptly at 12:30!&nbsp;</li>
<li>Search the room of your desired <strong>track&nbsp;</strong>(see the
                                            schedule below).
                                        </li>
<li>You may also attend the Award Ceremony and the Reception.</li>
</ul><h4>Attend on Zoom:</h4><ul>
<li>You may <strong>only</strong>&nbsp;view
                                            the&nbsp;<strong>Presentations</strong>, not the Expo and Awards.
                                        </li>
<li><strong>Each Track</strong> is held in a <strong>separate Zoom
                                            Room</strong>.
                                        </li>
<li>Plan to click the <a href="/">I2G
                                            Home Page</a> <strong> by 12:20&nbsp;</strong>to find and join a
                                            track!
                                        </li>
<li>Access to <strong>Zoom rooms </strong> will appear in the Schedule below
                                            and in the <a href="/">I2G Home
                                                Page</a><strong>&nbsp;</strong>on the event
                                            day<strong>&nbsp;after&nbsp;12:20!</strong></li>
<li>Sign in <strong>your Zoom account,&nbsp;</strong>make sure your
                                            <strong>&ldquo;Display Name&rdquo;</strong> is your Full Name.
                                        </li>
<li><strong>Click the button&nbsp;</strong>of the desired&nbsp;<strong>Track
                                            #&nbsp;</strong>(passcode is:&nbsp;&nbsp;I2G).
                                        </li>
<li>Presentations will <strong>start promptly at 12:30</strong>!&nbsp;&nbsp;
                                        </li>
<li>You may change Zoom Room to change track!</li>
</ul><div>
<h2 class="ea-section-title">EXPO: POSTERS AND DEMOS</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">Room:
                                                    </th>
<th scope="col">
                                                        Gym
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">9:30
                                                    </th>
<td>
<p>
                                                            Registration and Coffee</p>
</td>
</tr>
<tr>
<th scope="row">10:00
                                                    </th>
<td>
<p>
                                                            Demos and Posters - Lunch Boxes</p>
</td>
</tr>
<tr>
<th scope="row">
                                                        12:00
                                                    </th>
<td>
<p>
                                                            Networking - Transition to Presentations</p>
</td>
</tr>
</tbody>
</table></div>
</section><div>
<h2 class="ea-section-title">PRESENTATIONS</h2>
</div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead></thead>
<tbody>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
</tr>
<tr>
<th scope="col">
<gg-icon></gg-icon>
</th>
<th scope="col"><span><strong>Zoom
                                                                            1</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            2</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            3</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            4</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            5</strong></span></th>
</tr>
<tr>
<th scope="col">&nbsp;
                                                    </th>
<th scope="col">
                                                        Track 1
                                                    </th>
<th scope="col">
                                                        Track 2
                                                    </th>
<th scope="col">
                                                        Track 3
                                                    </th>
<th scope="col">
                                                        Track 4
                                                    </th>
<th scope="col">
                                                        Track 5
                                                    </th>
</tr>
</tbody>
<tbody>
<tr>
<th scope="row">
                                                        &nbsp;
                                                    </th>
<td>
<p>AgTech
                                                        </p>
</td>
<td>
<p>
<b>Process</b></p>
</td>
<td>
<p>Safety
                                                        </p>
</td>
<td>
<p>
<b>System</b></p>
</td>
<td>
<p>Waste</p>
</td>
</tr>
<tr>
<th scope="row">12:30
                                                    </th>
<td id="hover11">
<span>Team</span>
</td>
<td id="hover12">
<span>Team</span>
</td>
<td id="hover13">
<span>Team</span>
</td>
<td id="hover14">
<span>Team</span>
</td>
<td id="hover15">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:00
                                                    </th>
<td id="hover21">
<span>Team</span>
</td>
<td id="hover22">
<span>Team</span>
</td>
<td id="hover23">
<span>Team</span>
</td>
<td id="hover24">
<span>Team</span>
</td>
<td id="hover25">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:30
                                                    </th>
<td id="hover31">
<span>Team</span>
</td>
<td id="hover32">
<span>Team</span>
</td>
<td id="hover33">
<span>Team</span>
</td>
<td id="hover34">
<span>Team</span>
</td>
<td id="hover35">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:00
                                                    </th>
<td id="hover41">
<span>Team</span>
</td>
<td id="hover42">
<span>Team</span>
</td>
<td id="hover43">
<span>Team</span>
</td>
<td id="hover44">
<span>Team</span>
</td>
<td id="hover45">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:30
                                                    </th>
<td id="hover51">
<span>Team</span>
</td>
<td id="hover52">
<span>Team</span>
</td>
<td id="hover53">
<span>Team</span>
</td>
<td id="hover54">
<span>Team</span>
</td>
<td id="hover55">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">3:00
                                                    </th>
<td id="hover61">
<span>Team</span>
</td>
<td id="hover62">
<span>Team</span>
</td>
<td id="hover63">
<span>Team</span>
</td>
<td id="hover64">
<span>Team</span>
</td>
<td id="hover65">
<span>Team</span>
</td>
</tr>
<tr></tr>
</tbody>
</table></div>
</section><p><strong>CEE&nbsp;+&nbsp;EngSL</strong></p><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
</tr>
<tr>
<th scope="col">
<gg-icon></gg-icon>
</th>
<th scope="col"><span><strong>Zoom
                                                                            6+7</strong></span></th>
</tr>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 6
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">
                                                        &nbsp;
                                                    </th>
<td>
<p><b>Civil &amp;
                                                            Environmental&nbsp;</b></p>
</td>
</tr>
<tr>
<th scope="row">12:30
                                                    </th>
<td id="hover16">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:00
                                                    </th>
<td id="hover26">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:30
                                                    </th>
<td id="hover36">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 7
                                                    </th>
</tr>
<tr>
<th scope="row">
                                                        &nbsp;
                                                    </th>
<td>
<p><b>Service Learning</b></p>
</td>
</tr>
<tr>
<th scope="row">2:00
                                                    </th>
<td id="hover17">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:30
                                                    </th>
<td id="hover27">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">3:00
                                                    </th>
<td id="hover37">
<span>Team</span>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
</tr>
<tr>
<th scope="col">
<gg-icon></gg-icon>
</th>
<th scope="col"><span><strong>Zoom
                                                                            8</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            9</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            10</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            11</strong></span></th>
</tr>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 8
                                                    </th>
<th scope="col">
                                                        Track 9
                                                    </th>
<th scope="col">
                                                        Track 10
                                                    </th>
<th scope="col">
                                                        Track 11
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">
                                                        &nbsp;
                                                    </th>
<td>
<p><b>Code</b></p>
</td>
<td>
<p><b>Computer</b></p>
</td>
<td>
<p><b>Data</b></p>
</td>
<td>
<p><b>User</b></p>
</td>
</tr>
<tr>
<th scope="row">12:30
                                                    </th>
<td id="hover18">
<span>Team</span>
</td>
<td id="hover19">
<span>Team</span>
</td>
<td id="hover110">
<span>Team</span>
</td>
<td id="hover111">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">12:50
                                                    </th>
<td id="hover28">
<span>Team</span>
</td>
<td id="hover29">
<span>Team</span>
</td>
<td id="hover210">
<span>Team</span>
</td>
<td id="hover211">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:10
                                                    </th>
<td id="hover38">
<span>Team</span>
</td>
<td id="hover39">
<span>Team</span>
</td>
<td id="hover310">
<span>Team</span>
</td>
<td id="hover311">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:30
                                                    </th>
<td id="hover48">
<span>Team</span>
</td>
<td id="hover49">
<span>Team</span>
</td>
<td id="hover410">
<span>Team</span>
</td>
<td id="hover411">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:50
                                                    </th>
<td id="hover58">
<span>Team</span>
</td>
<td id="hover59">
<span>Team</span>
</td>
<td id="hover510">
<span>Team</span>
</td>
<td id="hover511">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:10
                                                    </th>
<td id="hover68">
<span>Team</span>
</td>
<td id="hover69">
<span>Team</span>
</td>
<td id="hover610">
<span>Team</span>
</td>
<td id="hover611">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:30
                                                    </th>
<td id="hover78">
<span>Team</span>
</td>
<td id="hover79">
<span>Team</span>
</td>
<td id="hover710">
<span>Team</span>
</td>
<td id="hover711">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:50
                                                    </th>
<td id="hover88">
<span>Team</span>
</td>
<td id="hover89">
<span>Team</span>
</td>
<td id="hover810">
<span>Team</span>
</td>
<td id="hover811">
<span>Team</span>
</td>
</tr>
</tbody>
</table></div>
</section><div>
<h2 class="ea-section-title">AWARDS &amp; RECEPTION</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">Room:
                                                    </th>
<th scope="col">
                                                        Gym
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">3:45
                                                    </th>
<td>
<p>
                                                            Award Ceremony</p>
</td>
</tr>
<tr>
<th scope="row">4:30
                                                    </th>
<td>
<p>
                                                            Reception</p>
</td>
</tr>
<tr></tr>
</tbody>
</table></div>
</section><div id="projects">
<div class="cms-table-block-wrap"><table class="cms-table-block-table" id="example">
<thead>
<tr>
<th>Track</th>
<th>Year-Semester</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
<th>Industry</th>
<th>More Info</th>
<th>&nbsp;</th>
<th>&nbsp;</th>
</tr>
</thead>
</table></div>
</div>
```

### Classes Used

`cms-table-block-table`, `cms-table-block-wrap`, `ea-back-link`, `ea-header`, `ea-section-title`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`

## Fall 2021 Event Page

### CMS Page Fields

- `slug`: `event-page-2021-fall`
- `route`: `/event-pages/2021-fall`
- `title`: `Fall 2021 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Fall 2021 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Fall 2021 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2021-fall">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<div><span><strong><span>Winners!&nbsp; Innovate to Grow - Fall
                                                        2021</span></strong></span></div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;</th>
<th scope="col">Track
                                                        1
                                                    </th>
<th scope="col">Track
                                                        2
                                                    </th>
<th scope="col">Track
                                                        3
                                                    </th>
<th scope="col">Track
                                                        4
                                                    </th>
<th scope="col">Track
                                                        5
                                                    </th>
<th scope="col">Track
                                                        6
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th>&nbsp;</th>
<td>
<p>
                                                            AgEngineering</p>
</td>
<td>
<p>
<b>AgTech</b></p>
</td>
<td>
<p>
<b>FoodTech</b></p>
</td>
<td>
<p>
<b>System</b></p>
</td>
<td>
<p>
<b>TomatoTech</b></p>
</td>
<td>
<p>
<b>Transportation</b></p>
</td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>Algae Prevention&nbsp;</b>
<p>CAP23 - Diamond J Dairy</p>
</td>
<td><b>The Data Loggers&nbsp;</b>
<p>CAP12 - Henry Miller Reclamation
                                                            District</p>
</td>
<td><b>Team 6&nbsp;</b>
<p>CAP06 - Milano Technical Group
                                                        </p>
</td>
<td><b>SCARA Calibration
                                                        Team&nbsp;</b>
<p>CAP15 - Omron</p>
</td>
<td><b>PouchTeks&nbsp;</b>
<p>CAP20 - Neil Jones Foods
                                                            (TomaTek)</p>
</td>
<td><b>A.B.S.S.&nbsp;</b>
<p>CAP04 - The Pi Shop</p>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>Civil &amp; Env.
                                        Engineering&nbsp; (CEE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;
                                                    </th>
<th scope="col">
                                                        Track 7
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td>
<p><b>Environment</b></p>
</td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>San JoAQuin Air
                                                        Quality&nbsp;</b>
<p>CEE03&nbsp;- San Joaquin&nbsp;Air
                                                            Pollution Control District</p>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">Track
                                                        8
                                                    </th>
<th scope="col">Track
                                                        9
                                                    </th>
<th scope="col">Track
                                                        10
                                                    </th>
<th scope="col">Track
                                                        11
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td>
<p><b>Code</b></p>
</td>
<td>
<p><b>Computer</b></p>
</td>
<td>
<p><b>Data</b></p>
</td>
<td>
<p><b>User</b></p>
</td>
</tr>
<tr>
<th scope="row">&nbsp;
                                                    </th>
<td><b>The
                                                        Diamond Cowboys&nbsp;</b>
<p>
                                                            CSE03&nbsp;- Diamond J Dairy</p>
</td>
<td><b>Project
                                                        ANJIL&nbsp;</b>
<p>
                                                            CSE05&nbsp;- Fresno Institute of Neuroscience</p>
</td>
<td>
<b>LADS&nbsp;</b>
<p>
                                                            CSE19&nbsp;- Sweep Energy</p>
</td>
<td><b>Cow
                                                        Cool Coders&nbsp;</b>
<p>
                                                            CSE04&nbsp;- Diamond J Dairy</p>
</td>
</tr>
</tbody>
</table></div>
</section><h4>Friday, December 17, 2021 -&nbsp;10:30AM - 4:00PM</h4><ul>
<li>10:30&nbsp;&nbsp;<b>Registration + Coffee</b>&nbsp;- Conference
                                            Center&nbsp;
                                        </li>
<li>11:00&nbsp;&nbsp;<b>Expo</b>&nbsp;(Posters - Demos) - Conference Center
                                        </li>
<li>12:45&nbsp;&nbsp;<b>Presentations</b>&nbsp;- Campus and&nbsp;Zoom (see
                                            schedule for Rooms)
                                        </li>
<li>15:00&nbsp;&nbsp;<b>Awards Ceremony</b>&nbsp;- Conference Center&nbsp;
                                        </li>
<li>15:30&nbsp;&nbsp;<b>Reception</b>&nbsp;- Conference Center</li>
</ul><a class="event-btn event-btn-gold" href="https://i2g-fall-2021.eventbrite.com" rel="noopener noreferrer" target="_blank">Register
                                            NOW</a>&nbsp;!
                                        <h4>Preparing for the Event</h4><ul>
<li><strong><a href="https://i2g-fall-2021.eventbrite.com" rel="noopener noreferrer" target="_blank">Register ASAP</a></strong>&nbsp; to attend
                                            <strong>in person</strong> or <strong>on zoom</strong>!
                                        </li>
<li>To attend on Zoom, ensure&nbsp;<strong>your account</strong> displays
                                            your <strong>Full Name</strong>.
                                        </li>
<li>Review schedule,&nbsp;projects, and teams (below):&nbsp;check for
                                            updates!
                                        </li>
<li>You may <strong>click on a team</strong> (e.g. CAP14) to open that
                                            <strong>team info</strong>.
                                        </li>
<li>Then, you may click the <strong>open/close icon</strong>&nbsp;to view
                                            <strong>project details</strong>.
                                        </li>
</ul><a class="event-btn event-btn-gold" href="/attendees">For Attendees</a><a class="event-btn event-btn-blue" href="/judges">For Judges</a><h4>Attend in Person:</h4><ul>
<li><strong>Mask required</strong> (provided if needed).</li>
<li><strong>Park </strong>in the reserved area in the Bellevue Lot (follow
                                            signs).
                                        </li>
<li><strong>Walk or shuttle</strong> to the Conference Center.</li>
<li>Pick up your <strong>badge </strong>at the Registration desk.</li>
<li>Registration and <strong>coffee </strong>start at 10:30.</li>
<li><strong>Expo </strong>doors open at 11:00 for student posters/demos.
                                        </li>
<li><strong>Lunch </strong>is served in boxes at the Conference Center.</li>
<li><strong>Presentations </strong>start promptly at 12:45!&nbsp;</li>
<li>Search the room of your desired <strong>track&nbsp;</strong>(see the
                                            schedule below).
                                        </li>
<li>You may also attend the Award Ceremony and the Reception.</li>
</ul><h4>Attend on Zoom:</h4><ul>
<li>You may <strong>only</strong>&nbsp;view
                                            the&nbsp;<strong>Presentations</strong>, not the Expo and Awards.
                                        </li>
<li><strong>Each Track</strong> is held in a <strong>separate Zoom
                                            Room</strong>.
                                        </li>
<li>Plan to click the <a href="/">I2G
                                            Home Page</a> <strong> by 12:40&nbsp;</strong>to find and join a
                                            track!
                                        </li>
<li>Access to <strong>Zoom rooms </strong> will appear in the Schedule below
                                            and in the <a href="/">I2G Home
                                                Page</a><strong>&nbsp;</strong>on the event
                                            day<strong>&nbsp;after&nbsp;12:30!</strong></li>
<li>Sign in <strong>your Zoom account,&nbsp;</strong>make sure your
                                            <strong>&ldquo;Display Name&rdquo;</strong> is your Full Name.
                                        </li>
<li><strong>Click the button&nbsp;</strong>of the desired&nbsp;<strong>Track
                                            #&nbsp;</strong>(passcode is:&nbsp;&nbsp;I2G).
                                        </li>
<li>Presentations will <strong>start promptly at 12:45</strong>!&nbsp;&nbsp;
                                        </li>
<li>You may change Zoom Room to change track!</li>
</ul><div>
<h2 class="ea-section-title">EXPO: POSTERS AND DEMOS</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">Room:
                                                    </th>
<th scope="col">
                                                        Conference Center
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">10:30
                                                    </th>
<td>
<p>
                                                            Registration and Coffee</p>
</td>
</tr>
<tr>
<th scope="row">11:00
                                                    </th>
<td>
<p>
                                                            Demos and Posters - Lunch Boxes</p>
</td>
</tr>
<tr>
<th scope="row">
                                                        12:30
                                                    </th>
<td>
<p>
                                                            Networking - Transition to Presentations</p>
</td>
</tr>
</tbody>
</table></div>
</section><div>
<h2 class="ea-section-title">PRESENTATIONS</h2>
</div><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
</thead>
<tbody>
<tr>
<th scope="col">&nbsp;
                                                    </th>
<th scope="col">
                                                        Track 1
                                                    </th>
<th scope="col">
                                                        Track 2
                                                    </th>
<th scope="col">
                                                        Track 3
                                                    </th>
<th scope="col">
                                                        Track 4
                                                    </th>
<th scope="col">
                                                        Track 5
                                                    </th>
<th scope="col">
                                                        Track 6
                                                    </th>
</tr>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
</tr>
<tr>
<th scope="col">
<gg-icon></gg-icon>
</th>
<th scope="col"><span><strong>Zoom
                                                                            1</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            2</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            3</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            4</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            5</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            6</strong></span></th>
</tr>
</tbody>
<tbody>
<tr>
<th scope="row">
                                                        &nbsp;
                                                    </th>
<td>
<p>
                                                            AgEngineering</p>
</td>
<td>
<p>
<b>AgTech</b></p>
</td>
<td>
<p>
<b>FoodTech</b></p>
</td>
<td>
<p>
<b>System</b></p>
</td>
<td>
<p>
<b>TomatoTech</b></p>
</td>
<td>
<p>
<b>Transportation</b></p>
</td>
</tr>
<tr>
<th scope="row">12:45
                                                    </th>
<td id="hover11">
<span>Team</span>
</td>
<td id="hover12">
<span>Team</span>
</td>
<td id="hover13">
<span>Team</span>
</td>
<td id="hover14">
<span>Team</span>
</td>
<td id="hover15">
<span>Team</span>
</td>
<td id="hover16">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:20
                                                    </th>
<td id="hover21">
<span>Team</span>
</td>
<td id="hover22">
<span>Team</span>
</td>
<td id="hover23">
<span>Team</span>
</td>
<td id="hover24">
<span>Team</span>
</td>
<td id="hover25">
<span>Team</span>
</td>
<td id="hover26">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:55
                                                    </th>
<td id="hover31">
<span>Team</span>
</td>
<td id="hover32">
<span>Team</span>
</td>
<td id="hover33">
<span>Team</span>
</td>
<td id="hover34">
<span>Team</span>
</td>
<td id="hover35">
<span>Team</span>
</td>
<td id="hover36">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:30
                                                    </th>
<td id="hover41">
<span>Team</span>
</td>
<td id="hover42">
<span>Team</span>
</td>
<td id="hover43">
<span>Team</span>
</td>
<td id="hover44">
<span>Team</span>
</td>
<td id="hover45">
<span>Team</span>
</td>
<td id="hover46">
<span>Team</span>
</td>
</tr>
<tr></tr>
</tbody>
</table></div>
</section><div><strong>Civil &amp;
                                        Environmental Engineering&nbsp;(CEE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 7
                                                    </th>
</tr>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
</tr>
<tr>
<th scope="col">
<gg-icon></gg-icon>
</th>
<th scope="col"><span><strong>Zoom
                                                                            7</strong></span></th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">
                                                        &nbsp;
                                                    </th>
<td>
<p><b>Environment</b></p>
</td>
</tr>
<tr>
<th scope="row">12:45
                                                    </th>
<td id="hover17">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:20
                                                    </th>
<td id="hover27">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:55
                                                    </th>
<td id="hover37">
<span>Team</span>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 8
                                                    </th>
<th scope="col">
                                                        Track 9
                                                    </th>
<th scope="col">
                                                        Track 10
                                                    </th>
<th scope="col">
                                                        Track 11
                                                    </th>
</tr>
<tr>
<th scope="col">
                                                        Room:
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        &nbsp;
                                                    </th>
</tr>
<tr>
<th scope="col">
<gg-icon></gg-icon>
</th>
<th scope="col"><span><strong>Zoom
                                                                            8</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            9</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            10</strong></span></th>
<th scope="col"><span><strong>Zoom
                                                                            11</strong></span></th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">
                                                        &nbsp;
                                                    </th>
<td>
<p><b>Code</b></p>
</td>
<td>
<p><b>Computer</b></p>
</td>
<td>
<p><b>Data</b></p>
</td>
<td>
<p><b>User</b></p>
</td>
</tr>
<tr>
<th scope="row">12:45
                                                    </th>
<td id="hover18">
<span>Team</span>
</td>
<td id="hover19">
<span>Team</span>
</td>
<td id="hover110">
<span>Team</span>
</td>
<td id="hover111">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:10
                                                    </th>
<td id="hover28">
<span>Team</span>
</td>
<td id="hover29">
<span>Team</span>
</td>
<td id="hover210">
<span>Team</span>
</td>
<td id="hover211">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">1:35
                                                    </th>
<td id="hover38">
<span>Team</span>
</td>
<td id="hover39">
<span>Team</span>
</td>
<td id="hover310">
<span>Team</span>
</td>
<td id="hover311">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:00
                                                    </th>
<td id="hover48">
<span>Team</span>
</td>
<td id="hover49">
<span>Team</span>
</td>
<td id="hover410">
<span>Team</span>
</td>
<td id="hover411">
<span>Team</span>
</td>
</tr>
<tr>
<th scope="row">2:25
                                                    </th>
<td id="hover58">
<span>Team</span>
</td>
<td id="hover59">
<span>Team</span>
</td>
<td id="hover510">
<span>Team</span>
</td>
<td id="hover511">
<span>Team</span>
</td>
</tr>
</tbody>
</table></div>
</section><div>
<h2 class="ea-section-title">AWARDS &amp; RECEPTION</h2>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">Room:
                                                    </th>
<th scope="col">
                                                        Conference Center
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">3:00
                                                    </th>
<td>
<p>
                                                            Award Ceremony</p>
</td>
</tr>
<tr>
<th scope="row">3:30
                                                    </th>
<td>
<p>
                                                            Reception</p>
</td>
</tr>
<tr></tr>
</tbody>
</table></div>
</section><div id="projects">
<div class="cms-table-block-wrap"><table class="cms-table-block-table" id="example">
<thead>
<tr>
<th>Track</th>
<th>Year-Semester</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
<th>Industry</th>
<th>More Info</th>
<th>&nbsp;</th>
<th>&nbsp;</th>
</tr>
</thead>
</table></div>
</div>
```

### Classes Used

`cms-table-block-table`, `cms-table-block-wrap`, `ea-back-link`, `ea-header`, `ea-section-title`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`

## Spring 2021 Event Page

### CMS Page Fields

- `slug`: `event-page-2021-spring`
- `route`: `/event-pages/2021-spring`
- `title`: `Spring 2021 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Spring 2021 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Spring 2021 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2021-spring">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<h4>Friday, May 14, 2021&nbsp;at 11:00AM - 2:00PM</h4><p>We will feature our student presentations <strong>online via
                                        Zoom</strong>:&nbsp;</p><ul>
<li>Presentations will <strong>start promptly at 11:00</strong>!</li>
<li>Plan to click the <a href="/">I2G Home Page</a>
<strong> by 10:50</strong> to find and join a track!
                                        </li>
<li>Access to <strong>Zoom rooms </strong> will appear in the Schedule below and
                                            in the <a href="/">I2G Home Page</a> <strong>on
                                                the event day</strong>.
                                        </li>
</ul><a class="event-btn event-btn-gold" href="https://www.eventbrite.com/e/innovate-to-grow-spring-2021-registration-139954847717" rel="noopener noreferrer" target="_blank">Register NOW !</a><h4>Preparing for the Event</h4><ul>
<li>
<a href="https://www.eventbrite.com/e/innovate-to-grow-spring-2021-registration-139954847717" rel="noopener noreferrer" target="_blank">Register ASAP</a>!
                                        </li>
<li>Check if <strong>your Zoom account</strong> displays your <strong>Full
                                            Name</strong>.
                                        </li>
<li>If you do not have a Zoom account: <a href="https://zoom.us/freesignup/" rel="noopener noreferrer" target="_blank">sign up for Zoom</a>.
                                        </li>
<li>You may review schedule, projects, and teams (being updated).</li>
<li>You may review detailed information:</li>
</ul><a class="event-btn event-btn-gold" href="/attendees">For Attendees</a><a class="event-btn event-btn-blue" href="/judges">For Judges</a><h4>Interactive Schedule (below)</h4><ul>
<li><strong>Each Track</strong> is held in a <strong>separate Zoom Room</strong>.
                                        </li>
<li>You may view the time of each team's presentation.</li>
<li>You may <strong>click on a team</strong> (e.g. CAP14) to open that <strong>team
                                            info</strong>.
                                        </li>
<li>Then, you may click the <strong>open/close icon</strong>&nbsp;to view
                                            <strong>project details</strong>.
                                        </li>
<li>You can <strong>click Track # (on event day)</strong> to access the desired
                                            Track.
                                        </li>
</ul><h4>The Day of the event:</h4><ul>
<li>Sign in <strong>your Zoom account</strong>.</li>
<li><strong>Click the button&nbsp;</strong>of the desired&nbsp;<strong>Track
                                            #</strong>.
                                        </li>
<li>Make sure your <strong>&ldquo;Display Name&rdquo;</strong> is your Full
                                            Name.
                                        </li>
<li>Enter the Passcode (I2G2021).</li>
<li>Welcome to the I2G presentations!</li>
</ul><div><strong>Engineering Capstone
                                        (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">&nbsp;</th>
<th scope="col">
                                                        Track 1
                                                    </th>
<th scope="col">
                                                        Track 2
                                                    </th>
<th scope="col">
                                                        Track 3
                                                    </th>
<th scope="col">
                                                        Track 4
                                                    </th>
<th scope="col">
                                                        Track 5
                                                    </th>
<th scope="col">
                                                        Track 6
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">Time
                                                    </th>
<td>
<p>AgEng</p>
</td>
<td>
<p><b>AgTech</b></p>
</td>
<td>
<p><b>Materials</b>
</p>
</td>
<td>
<p><b>Process</b>
</p>
</td>
<td>
<p><b>Tomato</b></p>
</td>
<td>
<p>
<b>Transportation</b></p>
</td>
</tr>
<tr>
<th scope="row">11:00
                                                    </th>
<td>
<span>CAP18</span>
<p>Diamond J Dairy</p>
</td>
<td>
<span>CAP13</span>
<p>California Ag Solutions</p>
</td>
<td>
<span>CAP15</span>
<p>Corigin Solutions</p>
</td>
<td>
<span>CAP12</span>
<p>Fresno Institute of Neuroscience</p>
</td>
<td>
<span>CAP02</span>
<p>The Morning Star Company</p>
</td>
<td>
<span>CAP14</span>
<p>BART</p>
</td>
</tr>
<tr>
<th scope="row">11:30
                                                    </th>
<td>
<span>CAP01</span>
<p>Merced College Ag Operations</p>
</td>
<td>
<span>CAP23</span>
<p>California Ag Solutions</p>
</td>
<td>
<span>CAP25</span>
<p>Corigin Solutions</p>
</td>
<td>
<span>CAP22</span>
<p>Fresno Institute of Neuroscience</p>
</td>
<td>
<span>CAP03</span>
<p>The Morning Star Company</p>
</td>
<td>
<span>CAP24</span>
<p>BART</p>
</td>
</tr>
<tr>
<th scope="row">12:00
                                                    </th>
<td>
<span>CAP11</span>
<p>Merced College Ag Operations</p>
</td>
<td>
<span>CAP28</span>
<p>Farm Data Systems</p>
</td>
<td>
<span>CAP16</span>
<p>Sweep Energy</p>
</td>
<td>
<span>CAP17</span>
<p>Blue Diamond Growers</p>
</td>
<td>
<span>CAP04</span>
<p>The Morning Star Company</p>
</td>
<td>
<span>CAP26</span>
<p>The Pi Shop</p>
</td>
</tr>
<tr>
<th scope="row">12:30
                                                    </th>
<td>
<span>CAP21</span>
<p>Merced College Ag Operations</p>
</td>
<td>
<span>CAP09</span>
<p>Milano Technical Group</p>
</td>
<td>
<span>CAP29</span>
<p>Jatco</p>
</td>
<td>
<span>CAP27</span>
<p>E&amp;J Gallo Winery</p>
</td>
<td>
<span>CAP05</span>
<p>The Morning Star Company</p>
</td>
<td>
<span>CAP10</span>
<p>Waymo</p>
</td>
</tr>
<tr>
<th scope="row">13:00
                                                    </th>
<td>
<span>CAP31</span>
<p>Merced College Ag Operations</p>
</td>
<td>
<span>CAP19</span>
<p>Milano Technical Group</p>
</td>
<td>&nbsp;</td>
<td>
<span>CAP08</span>
<p>Sensient Natural Ingredients</p>
</td>
<td>
<span>CAP06</span>
<p>The Morning Star Company</p>
</td>
<td>
<span>CAP20</span>
<p>Waymo</p>
</td>
</tr>
<tr>
<th scope="row">13:30
                                                    </th>
<td>&nbsp;</td>
<td>&nbsp;</td>
<td>&nbsp;</td>
<td>&nbsp;</td>
<td>
<span>CAP07</span>
<p>The Morning Star Company</p>
</td>
<td>
<span>CAP30</span>
<p>Waymo</p>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>Engineering Service
                                        Learning (EngSL)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 7
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">Time
                                                    </th>
<td>
<p><b>Non-Profits</b></p>
</td>
</tr>
<tr>
<th scope="row">11:00
                                                    </th>
<td>
<span>EngSL1</span>
<p>Fresno Discovery Center</p>
</td>
</tr>
<tr>
<th scope="row">11:30
                                                    </th>
<td>
<span>EngSL2</span>
<p>Healthy House</p>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering
                                        Capstone (CSE)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">
                                                        &nbsp;
                                                    </th>
<th scope="col">
                                                        Track 8
                                                    </th>
<th scope="col">
                                                        Track 9
                                                    </th>
<th scope="col">
                                                        Track 10
                                                    </th>
<th scope="col">
                                                        Track 11
                                                    </th>
</tr>
</thead>
<tbody>
<tr>
<th scope="row">Time
                                                    </th>
<td>
<p><b>Database</b></p>
</td>
<td>
<p><b>Display</b></p>
</td>
<td>
<p><b>Monitoring</b></p>
</td>
<td>
<p><b>Systems</b></p>
</td>
</tr>
<tr>
<th scope="row">11:00
                                                    </th>
<td>
<span>CSE26</span>
<p>Sweep Energy</p>
</td>
<td>
<span>CSE11</span>
<p>Veracruz Ventures</p>
</td>
<td>
<span>CSE08</span>
<p>Omron</p>
</td>
<td>
<span>CSE01</span>
<p>Cisco</p>
</td>
</tr>
<tr>
<th scope="row">11:20
                                                    </th>
<td>
<span>CSE27</span>
<p>Sweep Energy</p>
</td>
<td>
<span>CSE12</span>
<p>Veracruz Ventures</p>
</td>
<td>
<span>CSE09</span>
<p>Omron</p>
</td>
<td>
<span>CSE02</span>
<p>Cisco</p>
</td>
</tr>
<tr>
<th scope="row">11:40
                                                    </th>
<td>
<span>CSE14</span>
<p>United Way of Merced County</p>
</td>
<td>
<span>CSE13</span>
<p>Veracruz Ventures</p>
</td>
<td>
<span>CSE10</span>
<p>Omron</p>
</td>
<td>
<span>CSE03</span>
<p>Cisco</p>
</td>
</tr>
<tr>
<th scope="row">12:00
                                                    </th>
<td>
<p>
<span>CSE15</span>
</p>
<p>United Way of Merced County</p>
</td>
<td>
<span>CSE04</span>
<p>Agrecom</p>
</td>
<td>
<span>CSE22</span>
<p>Fresno Institute of Neuroscience</p>
</td>
<td>
<span>CSE17</span>
<p>BART</p>
</td>
</tr>
<tr>
<th scope="row">12:20
                                                    </th>
<td>
<p>
<span>CSE16</span>
</p>
<p>United Way of Merced County</p>
</td>
<td>
<span>CSE05</span>
<p>Agrecom</p>
</td>
<td>
<span>CSE23</span>
<p>Fresno Institute of Neuroscience</p>
</td>
<td>
<span>CSE18</span>
<p>BART</p>
</td>
</tr>
<tr>
<th scope="row">12:40
                                                    </th>
<td>
<span>CSE28</span>
<p>ISSNAF</p>
</td>
<td>
<span>CSE06</span>
<p>Agrecom</p>
</td>
<td>
<span>CSE19</span>
<p>BART</p>
</td>
<td>
<span>CSE24</span>
<p>Sweep Energy</p>
</td>
</tr>
<tr>
<th scope="row">13:00
                                                    </th>
<td>
<span>CSE29</span>
<p>ISSNAF</p>
</td>
<td>
<span>CSE07</span>
<p>Agrecom</p>
</td>
<td>
<span>CSE20</span>
<p>BART</p>
</td>
<td>
<span>CSE25</span>
<p>Sweep Energy</p>
</td>
</tr>
<tr>
<th scope="row">13:20
                                                    </th>
<td>
<span>CSE30</span>
<p>ISSNAF</p>
</td>
<td>&nbsp;</td>
<td>
<span>CSE21</span>
<p>BART</p>
</td>
<td>&nbsp;</td>
</tr>
</tbody>
</table></div>
</section><div id="projects">
<div class="cms-table-block-wrap"><table class="cms-table-block-table" id="example">
<thead>
<tr>
<th>Track</th>
<th>Year-Semester</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
<th>Industry</th>
<th>More Info</th>
<th>&nbsp;</th>
<th>&nbsp;</th>
</tr>
</thead>
</table></div>
</div>
```

### Classes Used

`cms-table-block-table`, `cms-table-block-wrap`, `ea-back-link`, `ea-header`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`

## Fall 2020 Event Page

### CMS Page Fields

- `slug`: `event-page-2020-fall`
- `route`: `/event-pages/2020-fall`
- `title`: `Fall 2020 Event Page`
- `page_css_class`: `event-page`
- `status`: start as `draft`, publish after preview.

### Block 1: Rich Text - Header and Navigation

- `heading`: `Fall 2020 Event Page`
- `heading_level`: `1`
- `body_html`:

```html
<div class="ea-header">
<a class="ea-back-link" href="/past-events">&larr; Past Events</a>
<p class="ea-subtitle">Fall 2020 &mdash; Innovate to Grow</p>
<p class="ea-text">Archived event page content from the legacy Innovate to Grow site. Use the interactive archive link for the searchable schedule and project experience.</p>
</div>
<div class="event-buttons">
<a class="event-btn event-btn-blue" href="/events/2020-fall">Interactive Schedule &amp; Projects</a>
<a class="event-btn event-btn-gold" href="/past-events">Past Events</a>
</div>
```

### Block 2: Embed - Legacy Video

- `src`: `https://www.youtube.com/embed/g_gTfLVWevg`
- `title`: `Fall 2020 Event Page video`
- `aspect_ratio`: `16:9`
- `allowfullscreen`: checked

### Block 3: Rich Text - Legacy Page Content

- `heading`: leave blank
- `body_html`:


```html
<h4>Message from the Dean</h4><p class="ea-text">Welcome and participation instructions, Mark
                                            Matsumoto, Dean, School of Engineering, University of California,
                                            Merced.</p><h4>Fall 2020 Information:</h4><a class="event-btn event-btn-blue" href="/events/2020-fall">Event</a><a class="event-btn event-btn-gold" href="/events/2020-fall">Schedule</a><a class="event-btn event-btn-blue" href="/events/2020-fall">Projects &amp;
                                            Teams</a><a class="event-btn event-btn-gold" href="/attendees">For Attendees</a><a class="event-btn event-btn-blue" href="/2020-fall-judges">For Judges</a><a class="event-btn event-btn-gold" href="/students">For Students</a><a class="event-btn event-btn-blue" href="/acknowledgement">Our Partners
                                            &amp; Sponsors</a><div><strong>Engineering Capstone (CAP)</strong></div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">Track 1</th>
<th scope="col">Track 2</th>
<th scope="col">Track 3</th>
<th scope="col">Track 4</th>
</tr>
</thead>
<tbody>
<tr>
<td>
<p><b>AgTech</b></p>
</td>
<td>
<p><b>Food<br/>
                                                        Processing</b></p>
</td>
<td>
<p><b>New<br/>
                                                        Products</b></p>
</td>
<td>
<p><b>Energy</b></p>
</td>
</tr>
<tr>
<td>
<p>Winner:</p>
</td>
<td>
<p>Winner:</p>
</td>
<td>
<p>Winner:</p>
</td>
<td>
<p>Winner:</p>
</td>
</tr>
<tr>
<td>
<p><span><strong>CAP17 - HBME Wetland Consulting</strong></span>
</p>
</td>
<td>
<p><span><strong>CAP12 - Suction Fan Optimization</strong></span>
</p>
</td>
<td>
<p><span><strong>CAP20 - G.A.S.S. Engineering</strong></span>
</p>
</td>
<td>
<p><span><strong>CAP15 - Green Street Team</strong></span>
</p>
</td>
</tr>
<tr>
<td>Click for teams information</td>
<td>Click for teams information</td>
<td>Click for teams information</td>
<td>Click for teams information</td>
</tr>
<tr>
<td>
<span>CAP01</span>
</td>
<td>
<span>CAP09</span>
</td>
<td>
<span>CAP16</span>
</td>
<td>
<span>CAP23</span>
</td>
</tr>
<tr>
<td>
<span>CAP02</span>
</td>
<td>
<span>CAP04</span>
</td>
<td>
<span>CAP11</span>
</td>
<td>
<span>CAP19</span>
</td>
</tr>
<tr>
<td>
<span>CAP22</span>
</td>
<td>
<span>CAP05</span>
</td>
<td>
<span>CAP20</span>
</td>
<td>
<span>CAP03</span>
</td>
</tr>
<tr>
<td>
<span>CAP24</span>
</td>
<td>
<span>CAP12</span>
</td>
<td>
<span>CAP21</span>
</td>
<td>
<span>CAP06</span>
</td>
</tr>
<tr>
<td>
<span>CAP10</span>
</td>
<td>
<span>CAP13</span>
</td>
<td>
<span>CAP18</span>
</td>
<td>
<span>CAP07</span>
</td>
</tr>
<tr>
<td>
<span>CAP17</span>
</td>
<td>
<span>CAP14</span>
</td>
<td>
<span>CAP15</span>
</td>
<td>
<span>CAP08</span>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>Engineering Service Learning (EngSL)</strong>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">Track 5</th>
</tr>
</thead>
<tbody>
<tr>
<td>
<p><b>Service<br/>
                                                        Learning</b></p>
</td>
</tr>
<tr>
<td>
<p>Winner:</p>
</td>
</tr>
<tr>
<td>
<p><strong><span>EngSL1&nbsp;- Project Protect</span></strong>
</p>
</td>
</tr>
<tr>
<td>
<p>Click for teams information</p>
</td>
</tr>
<tr>
<td>
<span>EngSL1</span>
</td>
</tr>
<tr>
<td>
<span>EngSL2</span>
</td>
</tr>
</tbody>
</table></div>
</section><div><strong>Software Engineering Capstone (CSE)</strong>
</div><section>
<div class="schedule-page-agenda-wrap"><table class="schedule-page-agenda-table">
<thead>
<tr>
<th scope="col">Track 6</th>
<th scope="col">Track 7</th>
</tr>
</thead>
<tbody>
<tr>
<td>
<p><b>Business<br/>
                                                        Problems</b></p>
</td>
<td>
<p><b>Software<br/>
                                                        Problems</b></p>
</td>
</tr>
<tr>
<td>
<p>Winner:</p>
</td>
<td>Winner:</td>
</tr>
<tr>
<td>
<p><span><strong>CSE08 - Mace</strong></span>
</p>
</td>
<td>
<p><span><strong>CSE04 - Helping Hands</strong></span>
</p>
</td>
</tr>
<tr>
<td>
<p>Click for teams information</p>
</td>
<td>
<p>Click for teams information</p>
</td>
</tr>
<tr>
<td>
<span>CSE12</span>
</td>
<td>
<span>CSE15</span>
</td>
</tr>
<tr>
<td>
<span>CSE13</span>
</td>
<td>
<span>CSE16</span>
</td>
</tr>
<tr>
<td>
<span>CSE14</span>
</td>
<td>
<span>CSE17</span>
</td>
</tr>
<tr>
<td>
<span>CSE06</span>
</td>
<td>
<span>CSE01</span>
</td>
</tr>
<tr>
<td>
<span>CSE07</span>
</td>
<td>
<span>CSE02</span>
</td>
</tr>
<tr>
<td>
<span>CSE08</span>
</td>
<td>
<span>CSE03</span>
</td>
</tr>
<tr>
<td>
<span>CSE09</span>
</td>
<td>
<span>CSE04</span>
</td>
</tr>
<tr>
<td>
<span>CSE10</span>
</td>
<td>
<span>CSE05</span>
</td>
</tr>
<tr>
<td>
<span>CSE11</span>
</td>
</tr>
</tbody>
</table></div>
</section><div id="projects">
<div class="cms-table-block-wrap"><table class="cms-table-block-table" id="example">
<thead>
<tr>
<th>Details</th>
<th>Track</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
</tr>
</thead>
<tfoot>
<tr>
<th>Details</th>
<th>Track</th>
<th>Class</th>
<th>Team#</th>
<th>Team Name</th>
<th>Project Title</th>
<th>Organization</th>
</tr>
</tfoot>
</table></div>
</div>
```

### Classes Used

`cms-table-block-table`, `cms-table-block-wrap`, `ea-back-link`, `ea-header`, `ea-subtitle`, `ea-text`, `event-btn`, `event-btn-blue`, `event-btn-gold`, `event-buttons`, `schedule-page-agenda-table`, `schedule-page-agenda-wrap`
