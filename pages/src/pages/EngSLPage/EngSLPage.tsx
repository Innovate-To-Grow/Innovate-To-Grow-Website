import { Link } from 'react-router-dom';
import './EngSLPage.css';

export const EngSLPage = () => {
  return (
    <div className="engsl-page">
      <h1 className="engsl-page-title">About Engineering Service Learning</h1>

      <div className="engsl-content">
        <div className="engsl-image-placeholder" />

        <div className="engsl-text-content">
          <h2 className="engsl-section-title">
            <a
              href="http://engineeringservicelearning.ucmerced.edu/"
              target="_blank"
              rel="noopener noreferrer"
            >
              Engineering Service Learning
            </a>
          </h2>

          <p className="engsl-text">
            This UC Merced's cornerstone engineering experience, designed to expose first-year
            students to the power of engineering. Through continuing partnerships with local
            nonprofits, students design meaningful solutions to the challenges their partners face.
          </p>

          <p className="engsl-text">Unique opportunities include:</p>

          <ul className="engsl-list">
            <li>Participation by students from all majors and grade levels</li>
            <li>Spans the course of a student's undergraduate career</li>
            <li>
              Developing ties to their communities through relationships with local nonprofits
            </li>
          </ul>

          <p className="engsl-text">
            We expect more than 300 people this year from industry, the community and K-12 schools,
            plus our UC Merced students and faculty and staff members.
          </p>

          <h3 className="engsl-subsection-title">How to Register?</h3>

          <p className="engsl-text">
            First, register for the lecture and then register for the corresponding lab, which would
            be your team you are placed within. The lab is more important than the lecture. Review
            the different{' '}
            <a
              href="http://engineeringservicelearning.ucmerced.edu/teams-0"
              target="_blank"
              rel="noopener noreferrer"
            >
              research teams
            </a>
            .
          </p>

          <p className="engsl-text">
            The CRN for the lecture is 30459 (lower division), or 30463 (upper division).
          </p>

          <p className="engsl-text">
            The class starts as a 1 unit class but if you wish to have a leadership role then it
            turns into 2 units. Review the{' '}
            <a
              href="http://engineeringservicelearning.ucmerced.edu/teams/team-structure"
              target="_blank"
              rel="noopener noreferrer"
            >
              process
            </a>
            .
          </p>

          <p className="engsl-text">
            Schedule conflicts for the lecture only can be accommodated. Please send lecture override
            requests to{' '}
            <a href="mailto:esl@ucmerced.edu">esl@ucmerced.edu</a> with the following information:
          </p>

          <ul className="engsl-list">
            <li>Name</li>
            <li>Student Id</li>
            <li>ENGR 097 (lower division) or ENGR 197 (upper division)</li>
          </ul>

          <p className="engsl-text">
            For current Teams &amp; Student Projects, visit{' '}
            <Link to="/projects-teams">Teams &amp; Projects</Link>.
          </p>
        </div>
      </div>
    </div>
  );
};
