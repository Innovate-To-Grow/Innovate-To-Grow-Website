import { Link } from 'react-router-dom';
import './ProjectSubmissionPage.css';

export const ProjectSubmissionPage = () => {
  return (
    <div className="submission-page">
      <h1 className="submission-page-title">Project Submission</h1>

      <section className="submission-section">
        <h2 className="submission-section-title">Submit a Project</h2>
        <a
          href="https://forms.gle/ihQG5ieEvCKfYP5n9"
          target="_blank"
          rel="noopener noreferrer"
          className="submission-button"
        >
          Click Here to Submit Your Project
        </a>
      </section>

      <section className="submission-section">
        <h2 className="submission-section-title">What is "Capstone" Project?</h2>
        <p className="submission-text">
          The Innovate to Grow (I2G) program provides senior and graduating engineering students
          with the opportunity to work on their Engineering Capstone and Software Engineering class
          through addressing a real world problem posed by an external organization. I2G is currently
          a semester-long program, and a project is assigned to a team of 3-5 students with
          majors/skills that match the project requirements. I2G provides the opportunity to sponsor
          organizations to perform studies, conjecture solutions to problems, test ideas, and assess
          students on real work. The School of Engineering has the following five Departments and
          Engineering Majors: Mechanical, Civil and Environmental, Chemical and Material Science,
          Biological, and Computer Science.
        </p>
      </section>

      <section className="submission-section">
        <h2 className="submission-section-title">How are teams and projects selected?</h2>
        <p className="submission-text">
          The list of project summaries proposed by partners, and applicable to Engineering or
          Software Capstone, are presented by the Professors of the respective class for the students
          to review and select in a web poll. Based on the results, the Professor forms teams to
          optimize the student's preferences, the engineering majors required for the project, and
          the priority of the proposed projects.
        </p>
      </section>

      <section className="submission-section">
        <h2 className="submission-section-title">How is Capstone related to Innovate to Grow?</h2>
        <p className="submission-text">
          Innovate to Grow is the event in which we showcase our student's engineering design talent
          from the Capstone projects. The Final Design Review is embedded in the event program, which
          culminates in a multi-faceted competition that also encompasses the School of Engineering's
          signature programs: Engineering Capstone, Software Engineering Capstone, and Engineering
          Service Learning.
        </p>
      </section>

      <section className="submission-section">
        <h2 className="submission-section-title">
          Can I see examples of Capstone projects and proposals?
        </h2>
        <p className="submission-text">
          If you would like to see projects to get ideas for your submission you may:
        </p>
        <ul className="submission-list">
          <li>
            Search the database of final summaries of{' '}
            <Link to="/past-projects">past projects</Link> of Innovate to Grow since 2012.
          </li>
          <li>
            View{' '}
            <Link to="/sample-proposals">samples of project proposals</Link> submitted by other
            organizations, including Engineering and Software problems.
          </li>
        </ul>
      </section>

      <section className="submission-section">
        <h2 className="submission-section-title">
          What are the agreements for a Capstone - I2G project?
        </h2>
        <p className="submission-text">
          You may find more information about execution of projects, agreements, and timelines at:
        </p>
        <ul className="submission-list">
          <li>
            Template of the{' '}
            <a
              href="https://i2g.ucmerced.edu/I2G-student-agreement"
              target="_blank"
              rel="noopener noreferrer"
            >
              Student Agreement
            </a>
            .
          </li>
          <li>
            Template of the{' '}
            <a
              href="https://i2g.ucmerced.edu/I2G-project-sponsor-acknowledgement"
              target="_blank"
              rel="noopener noreferrer"
            >
              Partner Agreement
            </a>
            .
          </li>
          <li>
            Template of the{' '}
            <a
              href="https://i2g.ucmerced.edu/template-email-team-students"
              target="_blank"
              rel="noopener noreferrer"
            >
              Project - Team with signed agreements
            </a>
            .
          </li>
        </ul>
      </section>

      <section className="submission-section">
        <h2 className="submission-section-title">Where can I find more information?</h2>
        <p className="submission-text">
          You may find more information about execution of projects, agreements, and timelines at:{' '}
          <a
            href="https://i2g.ucmerced.edu/FAQs"
            target="_blank"
            rel="noopener noreferrer"
          >
            Frequently Asked Questions (FAQs)
          </a>
        </p>
      </section>

    </div>
  );
};
