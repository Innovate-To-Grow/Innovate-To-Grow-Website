import { Link } from 'react-router-dom';
import './EventPreparationPage.css';

export const EventPreparationPage = () => {
  return (
    <div className="student-page">
      <h1 className="student-page-title">
        Students &amp; Teams - I2G Event Preparation
      </h1>

      <section className="student-section">
        <h2 className="student-section-title">Intro to I2G - Program and Event</h2>
        <p className="student-text">
          Innovate to Grow (I2G) is a unique "experiential learning" program that engages external
          partner organizations with teams of students who design systems to solve complex,
          real-world problems.
        </p>
        <p className="student-text">
          At the end of each semester, the work completed by the student teams culminates in the
          Innovate to Grow event. Teams are assigned to tracks, where they present their projects to
          judges and public attendees, followed by Q&amp;A. Judges will then select the track
          winners, which will be announced on the web site (or an award ceremony).
        </p>
        <p className="student-text">
          Notice that the I2G showcase is a great opportunity for students to communicate their
          projects and experience to the public, to participate in an engineering challenge, to
          engage with professionals, and to find internships and job opportunities. You may see more
          information <Link to="/about">about I2G</Link>.
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Event Preparation</h2>
        <p className="student-text">
          Innovate to Grow (I2G) is currently executed in multiple Zoom rooms (tracks). Here
          students and teams may find important info to prepare for the event.
        </p>
        <p className="student-text">
          <strong>Zoom info</strong>: The zoom rooms (links) will be activated on the I2G home page
          a few minutes before the event starts. You do not need the zoom links in advance.
        </p>
        <p className="student-text">
          <strong>No Registration needed</strong>: Students that are part of a class in the current
          semester I2G event are <strong>automatically registered</strong>. Students{' '}
          <strong>MUST NOT register for I2G in Eventbrite</strong>: this would complicate sorting
          through registrations to manage judges and attendees!
        </p>
        <p className="student-text">
          In summary: all students need to do on the day of the event is to go to the I2G home
          page.
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Team Name</h2>
        <p className="student-text">
          Unique and creative Team Names were started by students early on in Innovate to Grow, and
          has since become a tradition. If a team does not want to invent a unique name, it helps to
          have a short name for the project.
        </p>
        <p className="student-text">Guidelines for the "Team Name":</p>
        <ul className="student-list">
          <li>Can be creative, but...</li>
          <li>Must not be offensive or inappropriate</li>
          <li>Maximum 36 characters</li>
          <li>Will be reviewed and approved</li>
        </ul>
        <p className="student-text">
          You may view all team names and project abstracts since 2012 in the{' '}
          <Link to="/past-projects">Past Projects</Link>.
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Abstract</h2>
        <p className="student-text">
          The abstract is a short summary of the background, the problem/objective, and the
          solution/deliverable. Similarly to the abstract in a journal, or an executive summary of a
          business plan or project, it is intended to quickly summarize the goals and
          accomplishments.
        </p>
        <p className="student-text">
          The abstract of a Capstone / I2G project will be published and searchable in the Innovate
          to Grow website, and likely the most read content of I2G teams. Therefore, it should
          highlight excellence in engineering education, professionality, and communication. It
          should be written clearly and concisely for a general audience. Since it is for public
          release, it must not contain confidential information. You may view all team names and
          project abstracts since 2012 in the <Link to="/past-projects">Past Projects</Link>.
        </p>
        <p className="student-text">The best approach to write your Capstone abstract:</p>
        <ol className="student-ordered-list">
          <li>
            Review the original background, problem, objective of the project summary as proposed
            by the client and shared at the beginning of the semester.
          </li>
          <li>Condense the background, problem, objective.</li>
          <li>Add the final result of what you did, or what you delivered.</li>
          <li>Check spelling, punctuation, spaces, Caps, acronyms, ...</li>
          <li>
            Review to make sure it is fluid, logical, precise, succinct, and correct (client,
            users, etc.)
          </li>
          <li>Ask feedback and approval by your client for public release.</li>
        </ol>
        <p className="student-text">Recommended abstract structure:</p>
        <ul className="student-list">
          <li>Client is/does ....</li>
          <li>The problem is that ... or ... our project was to ...</li>
          <li>
            We (or Our team) designED (PAST tense) something with such and such that DOES this and
            that
          </li>
          <li>
            The model/tool IS / SHALL BE used by ... or was tested by ... and SHALL produce this
            benefit.
          </li>
        </ul>
        <p className="student-text">Abstract common problems:</p>
        <ul className="student-list">
          <li>Spelling errors, lowercases when should be Caps.</li>
          <li>
            It sounds like a plan (our task is to ... or we will do) rather than project result.
          </li>
          <li>Confusion between the problem and the solution.</li>
          <li>
            Unclear whether the technical description was the status quo or the result of your work.
          </li>
          <li>
            Rough sentences: without subject, or verb, wrong punctuation, repeated words, etc.
          </li>
        </ul>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Slides</h2>
        <p className="student-text">
          Please follow the additional guidelines provided to your class. These are recommendations
          for ALL slides and presentations to provide context and conclude with action.
        </p>
        <h3 className="student-section-subtitle">First Slide</h3>
        <ul className="student-list">
          <li>Team name</li>
          <li>Team number (e.g. CAP-123 or CSE-321)</li>
          <li>Project title</li>
          <li>Industry partner name - use a logo if possible</li>
          <li>Optionally, indicate the client/mentor name(s), if they OKed</li>
        </ul>
        <h3 className="student-section-subtitle">Every Slide Footer</h3>
        <p className="student-text">
          Throughout the presentation, place a footer with:
        </p>
        <ul className="student-list">
          <li>Team name</li>
          <li>Team number</li>
          <li>Project title</li>
          <li>Industry partner name</li>
          <li>Slide number</li>
        </ul>
        <p className="student-text">
          This will remind attendees and judges who you are even if they come in late or forget.
        </p>
        <h3 className="student-section-subtitle">Last Slide</h3>
        <ul className="student-list">
          <li>
            The same information as the first slide (may use smaller fonts or logos)
          </li>
          <li>
            Team members' names with corresponding contact info (see contact info guidelines)
          </li>
        </ul>
        <p className="student-text">
          Very importantly, during the presentation, remember to end and stay on this last slide (no
          "Questions?" nor "Thank you!" slide after that or the audience loses your info).
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Poster</h2>
        <p className="student-text">
          The team's goal at an expo should be to stop people to engage them. In case someone wants
          to read (less likely), then the content of the poster should be clear and concise.
          Therefore, the most important part of the poster is to identify:
        </p>
        <ul className="student-list">
          <li>Team name</li>
          <li>Team number (e.g. CAP-123 or CSE-321)</li>
          <li>Project title</li>
          <li>Industry partner name - use a logo if possible</li>
          <li>Optionally, indicate the client/mentor name(s), if they OKed</li>
          <li>The students with corresponding contact info (see contact info guidelines)</li>
        </ul>
        <p className="student-text">
          This information should all be at the top (where people walking by look at first, along
          with faces).
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Contact Info</h2>
        <p className="student-text">
          These recommendations for how to present the team members' contact information will
          facilitate the audience to recognize you, write your name/email, remember you later:
        </p>
        <ul className="student-list">
          <li>Contact information of a student placed under the corresponding name</li>
          <li>Use a personal email (unless you will check or forward your school email)</li>
          <li>Make your contact info very easy to read (shorter text, larger font)</li>
          <li>
            Do not write "Personal Email:" or even "Email: ...." — everyone knows that a@b.c is an
            email
          </li>
          <li>
            Do not write HTTPS://WWW. .... just linkedin.com/in/johndoe/ or Linkedin: johndoe
          </li>
          <li>
            Get a shorter LinkedIn handle rather than the default: john-doe-6b21ba797f
          </li>
          <li>
            Preferably, place the corresponding student photo near the contact info.
          </li>
        </ul>
        <p className="student-text">
          <strong>Examples</strong>:
        </p>
        <p className="student-text">
          Firstname Lastname<br />
          email@whatever.com<br />
          linkedin.com/in/linkedin-name
        </p>
        <p className="student-text">
          Stefano Foresti<br />
          email@stefanoforesti.com<br />
          linkedin.com/in/steforesti
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Video Preparation</h2>
        <p className="student-text">
          Please read the detailed{' '}
          <Link to="/video-preparation">instructions on how to prepare video presentations</Link>{' '}
          including:
        </p>
        <ul className="student-list">
          <li>Content preparation</li>
          <li>Presentation and slides structure</li>
          <li>Video recording recommendations</li>
        </ul>
        <p className="student-text">
          Please consult with your class instructor for further details including:
        </p>
        <ul className="student-list">
          <li>Deadlines for submission</li>
          <li>Specific requirements in content preparation</li>
          <li>Content and files upload instructions</li>
          <li>Other requirements</li>
        </ul>
        <p className="student-text">
          Please notice that your video may be stitched and compiled in a video file for a whole
          track, and that technical hosts will start-pause the video based on the event schedule and
          the live Q&amp;A sessions. Therefore, please consider these{' '}
          <strong>important additional requirements for video delivery during an online event</strong>.
        </p>
        <h3 className="student-section-subtitle">Video Start</h3>
        <ul className="student-list">
          <li>
            Start the video on mute on the first slide (Team #, Name, Project, Client, Students).
          </li>
          <li>Start speaking 5 seconds after starting the video on the first slide.</li>
        </ul>
        <p className="student-text">
          This will allow smooth transitions between presentations and Q&amp;As, as well as context
          for judges.
        </p>
        <h3 className="student-section-subtitle">Video End</h3>
        <ul className="student-list">
          <li>
            Conclude your presentation on the slide with Team #, Name, Project, Client, and the
            Students' contact info.
          </li>
          <li>
            At the end of your presentation and closing statements, continue the video recording on{' '}
            <strong>mute for 15 seconds on the last contact slide</strong>.
          </li>
        </ul>
        <p className="student-text">
          This will facilitate the tech hosts pausing the video after you have completed speaking,
          and keeping your last slide, which may persist during the Q&amp;A session: therefore, the
          judges keep having the context to write their forms, and attendees can note your info.
        </p>
        <p className="student-text">Notice:</p>
        <ul className="student-list">
          <li>
            It is counterproductive to end the presentation on "Thank you" or "Questions?" or "End
            of Slides".
          </li>
          <li>
            The time added to your video while muted during opening and closing slides will not
            count towards the maximum video length (of your class), because they may be cut in the
            stitching and video preparation process.
          </li>
        </ul>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Content Upload - File Naming</h2>
        <p className="student-text">
          I2G involves dozens of projects, partners, judges, and hundreds of students each semester.
          Since the beginning in 2012 I2G involved several hundreds of projects. All teams and
          abstracts can be searched in the <Link to="/past-projects">Past Projects</Link> section of
          the web site. All files related to projects videos, presentations, posters, reports are
          kept confidential and archived to be findable.
        </p>
        <p className="student-text">
          We need your cooperation to ensure that the files are named so that they are{' '}
          <strong>recognizable, sortable, and findable</strong>: this will further strengthen the
          program and the opportunities for Students, Partners and UC Merced.
        </p>
        <p className="student-text">
          When creating, sharing, and uploading files use this convention:
        </p>
        <p className="student-text">
          <strong>YYYY-Semester-PROgramTeam##-assignment.filetype</strong>
        </p>
        <p className="student-text">Where:</p>
        <ul className="student-list">
          <li>YYYY = the year</li>
          <li>
            Semester = 01-Spring and 08-Fall are the semester with a digit prior for sortability
          </li>
          <li>PROgram = CAP (Eng. Capstone) or CSE (Software Eng.)</li>
          <li>Assignment = video, slides, poster, report, other ....</li>
          <li>Filetype: depending on file</li>
        </ul>
        <p className="student-text">For instance:</p>
        <ul className="student-list">
          <li>2021-01-Spring-CAP03-video.mp4 — if ENGR 190 team 5 submits the video</li>
          <li>2022-08-Fall-CSE12-slides.ppt — if CSE120 team 12 submits the slides</li>
        </ul>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Team Information - Schedule Review</h2>
        <p className="student-text">
          Please review the schedule of the I2G event: please search in the navigation bar the link
          to the current semester, and links to the semester program are found there.
        </p>
        <p className="student-text">
          <strong>For the current semester</strong>, check the schedule and{' '}
          <Link to="/current-projects">current projects and teams</Link>.
        </p>
        <ol className="student-ordered-list">
          <li>Find your team number in the schedule (CAPxxx, CSExxx, CEExxx or EngSLxxx).</li>
          <li>Check if your Client is correctly listed in the schedule.</li>
          <li>
            Mouseover your team number and check if the popup shows your correct "Team Name -
            Project Title".
          </li>
          <li>
            Click on your team number, which shall open a datatable with team-project details. You
            may also find the details searching for your team in{' '}
            <Link to="/current-projects">Current Projects</Link>.
          </li>
          <li>
            Open your team details by clicking the icon/arrow, and check if they are correct:
            <ul className="student-list" style={{ marginTop: '0.5rem' }}>
              <li>Team Name</li>
              <li>Project Title</li>
              <li>Organization (client)</li>
              <li>Abstract</li>
              <li>Student Names</li>
            </ul>
          </li>
          <li>
            Check if any team member has a schedule conflict during your team's slot. Keep in mind
            that while the video is pre-recorded, the Q&amp;A session is live, so the team needs to
            be prepared to excel at the Q&amp;A session.
          </li>
        </ol>
        <p className="student-text">
          If there is a <strong>schedule conflict</strong> or if you find{' '}
          <strong>incorrect information</strong>, please{' '}
          <strong>contact immediately</strong> your instructor and{' '}
          <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">The Event Day - I2G Q&amp;A Session</h2>
        <p className="student-text">
          <strong>Team's time slot</strong>. The track is divided in time slots, and the zoom host
          will do the following in each team's slot:
        </p>
        <table className="student-table">
          <thead>
            <tr>
              <th>Phase</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Transition from previous team presentation (+/- 2 min based on schedule)</td>
              <td>
                <ul>
                  <li>Tech Host MUTES ALL participants</li>
                </ul>
              </td>
            </tr>
            <tr>
              <td>Pre-recorded Video (10-20 minutes depending on class)</td>
              <td>
                <ul>
                  <li>The Tech Host will share the student video presentation</li>
                  <li>
                    The Tech Host will unmute students before the end of the presentation
                  </li>
                  <li>
                    The Tech Host will pause the video on the final slide (with the QR Code for the
                    judging survey)
                  </li>
                </ul>
              </td>
            </tr>
            <tr>
              <td>Live Q/A (8-12 minutes depending on class)</td>
              <td>
                <ul>
                  <li>
                    The Tech Host will allow one student to share their screen with reference
                    materials (slide deck or simulation) during the Q/A
                  </li>
                  <li>The Moderator will read questions to students from the chat</li>
                  <li>
                    The Tech Host will resume the video with an intermission slide during the
                    transition
                  </li>
                  <li>
                    The Tech Host will remove screen sharing permissions from the student
                  </li>
                </ul>
              </td>
            </tr>
            <tr>
              <td>Transition to next presentation</td>
              <td>
                <ul>
                  <li>The Tech Host WILL MUTE all participants</li>
                </ul>
              </td>
            </tr>
          </tbody>
        </table>

        <p className="student-text" style={{ marginTop: '1.5rem' }}>
          <strong>Presence</strong>.
        </p>
        <ul className="student-list">
          <li>
            Students are not required to be present during the whole event (although, highly
            encouraged).
          </li>
          <li>
            Teams MUST join the zoom room of your designated track at the start of the event. If you
            cannot attend the whole event, please join your designated track's zoom room no less
            than 10-15 minutes before the scheduled start time of your video presentation.
          </li>
          <li>
            The presentation will start about the time on the schedule (+ or - 2 minutes).
          </li>
        </ul>

        <p className="student-text">
          <strong>Attire</strong>.
        </p>
        <ul className="student-list">
          <li>Dress business casual and have a professional presence.</li>
          <li>
            Ideally, use the same{' '}
            <Link to="/video-preparation">preparation as in the video recording</Link>.
          </li>
          <li>
            Use a proper background, possibly the{' '}
            <a
              href="https://ucmerced.box.com/s/rvd24ng4hyptg27rp5cposeo0b8ad6rl"
              target="_blank"
              rel="noopener noreferrer"
            >
              I2G approved virtual background
            </a>
            .
          </li>
          <li>
            Please make sure if you are using a zoom profile picture, it is professional.
          </li>
          <li>Audio: no background noise, test audio level.</li>
        </ul>

        <p className="student-text">
          <strong>Zoom</strong>.
        </p>
        <ul className="student-list">
          <li>Check the quality of the internet connection.</li>
          <li>Sign in your Zoom account.</li>
          <li>Click the Zoom Room # of your Track.</li>
          <li>Make sure your "Display Name" is your Full Name.</li>
          <li>Enter the Passcode.</li>
        </ul>
        <p className="student-text">
          The zoom tech host will know your names and make you co-host the designated student to
          deliver Q&amp;A slides - if needed.
        </p>

        <p className="student-text">
          <strong>Q&amp;A</strong>. Your team will be answering live Q&amp;A.
        </p>
        <ul className="student-list">
          <li>The moderator will speak the questions selected from chat.</li>
          <li>
            A designated team member may use the slides in case the judge asks a question that
            refers to a slide.
          </li>
          <li>
            Return to the final slide with contact info if your slides are still on screen.
          </li>
          <li>
            Be ready to respond to questions in case another team member can't for whatever reason.
          </li>
          <li>
            Avoid indecisions in selecting team members and hesitations when responding to
            questions.
          </li>
          <li>
            It is recommended that team members set up a backend communication channel (slack,
            texting, telegram, skype ...) so that they can synchronize without double speaking or
            speaking to each other in the Q&amp;A session.
          </li>
          <li>Thank the Judges - Attendees (optional).</li>
        </ul>
        <p className="student-text">
          Please communicate the designated student for sharing the screen to your instructor.
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Post Event</h2>
        <p className="student-text">
          <strong>Winners</strong>. At the end of the presentations, the evaluations by the judges
          will be compiled. The Winners will be announced on the I2G Home Page about an hour after
          the end of the presentations (3:30-4pm). Winners will receive a certificate in the mail.
          There are plans to build a wall plaque at the School of Engineering, where winners will be
          added.
        </p>
        <p className="student-text">
          <strong>Program Feedback</strong>. We appreciate if you take a moment to take this{' '}
          <a
            href="https://ucmerced.az1.qualtrics.com/jfe/form/SV_e4L1PyHidYuThEW"
            target="_blank"
            rel="noopener noreferrer"
          >
            Post Capstone &amp; I2G survey
          </a>{' '}
          to help us improve the program and experiential learning experience.
        </p>
      </section>

      <section className="student-section">
        <h2 className="student-section-title">Keep in Touch with Alma Mater</h2>
        <p className="student-text">
          <strong>Contact info</strong>. UC Alumni have the benefit of the student email address
          forever: take advantage of this great resource! It is advised that you store and forward
          your email @ucmerced.edu to your personal email, unless you plan to check your alumni
          email in the future: this is a great way to be contacted by UC Merced or Alumni in the
          future.
        </p>
        <p className="student-text">
          <strong>LinkedIn</strong>. It is advised that you set up or update your LinkedIn account
          for professional development, and connect to key contacts at the School of Engineering and
          Career Services.
        </p>
        <p className="student-text">
          <strong>Jobs and Internships</strong>. Contact your client for job or internship
          opportunities: they are the low hanging fruit in your job search. Also, use your Capstone
          experience with industry in your resume. Some Capstone projects may lead to a
          continuation: check with your partner if they are interested in continuing them, or offer
          to do so with a term job or internship. Being enthusiastic, curious and entrepreneurial
          will help you in career building.
        </p>
        <p className="student-text">
          <strong>Keep in touch</strong>.
        </p>
        <ul className="student-list">
          <li>We look forward to hearing your career moves.</li>
          <li>We are happy to invite you to participate as a Judge to a future I2G.</li>
          <li>
            We solicit that you propose and mentor projects, with the organization you work for.
          </li>
          <li>Please promote the I2G/Capstone program with your employer.</li>
        </ul>
      </section>
    </div>
  );
};
