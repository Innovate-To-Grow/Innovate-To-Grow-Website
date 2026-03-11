import { Link } from 'react-router-dom';
import './AboutPage.css';

export const AboutPage = () => {
  return (
    <div className="about-page">
      <h1 className="about-page-title">
        Engineering Solutions for Innovative Organizations
      </h1>

      <div className="about-content">
        <p className="about-lead">
          Innovate to Grow (I2G) is a unique "experiential learning" program that engages external
          partner organizations with teams of students who design systems to solve complex, real-world
          problems.
        </p>

        <p className="about-text">
          At the end of each semester, the work completed by the student teams culminates in the
          Innovate to Grow event, which features student-led research and highlights their project
          outcomes. The bi-annual Innovate to Grow event is a showcase of UC Merced student ingenuity
          and creativity, and the marquee event for the School of Engineering, drawing hundreds of
          industry leaders, community members, and entrepreneurs from the Central Valley, Silicon
          Valley, Southern California and beyond.
        </p>

        <p className="about-text">
          Innovate to Grow began in 2012 as the culminating event for the School of Engineering's
          Senior Capstone teams' final report, originating from an idea first sketched on a napkin by
          then–Dean Dan Hirleman. Since then, the Innovate to Grow program has evolved to encompass
          the following experiential learning classes and key threads of our campus's innovation
          culture:
        </p>

        <ul className="about-list">
          <li>
            <a
              href="https://i2g.ucmerced.edu/engineering-capstone"
              target="_blank"
              rel="noopener noreferrer"
            >
              Engineering Capstone
            </a>{' '}
            - CAP (formerly known as Innovation Design Clinic)
          </li>
          <li>
            <a
              href="https://i2g.ucmerced.edu/software-capstone"
              target="_blank"
              rel="noopener noreferrer"
            >
              Software Engineering Capstone
            </a>{' '}
            - CSE (formerly known as Mobile App Challenge, MAC)
          </li>
          <li>Civil &amp; Environmental Engineering Capstone - CEE</li>
          <li>
            <a
              href="https://engineeringservicelearning.ucmerced.edu/"
              target="_blank"
              rel="noopener noreferrer"
            >
              Engineering Service Learning
            </a>{' '}
            - ESL
          </li>
        </ul>

        <p className="about-text">
          In one year (two semesters) the Innovate to Grow projects, classes, and events involve
          approximately 500 students and 100 teams. The classes that are part of the Innovate to Grow
          program have grown since its inception, as our enrollments in engineering and computer
          science continue to grow rapidly.
        </p>

        <p className="about-text">
          Depending on the nature of the project, the amenability for multiple solutions or
          competition and the availability and interest of the industry mentors, a team may be paired
          1:1 with a partner/project, while other projects have two or more teams competing to
          produce competitive designs.
        </p>

        <p className="about-text">
          The projects tackled by the students involve a variety of industries, such as Agriculture,
          Food Processing, Water, Energy, Health Care, Medical Devices, Finance, Transportation,
          Construction, Materials, IT, Networking, and more.
        </p>

        <p className="about-text">
          Most student innovations are related to projects inspired by industry partners and
          community organizations where success might be measured by:
        </p>

        <ul className="about-list">
          <li>a system or process improvement for the partner's operations or plant;</li>
          <li>a prototype or invention that may lead to a product or patent application;</li>
          <li>a software application or system improvement;</li>
          <li>
            studies and prototypes for government labs or nonprofits in the local community.
          </li>
        </ul>

        <p className="about-text">
          Some of those innovations can help, or turn into, small businesses in the community. The
          innovation and entrepreneurial thinking embedded in our culture are signatures of our
          programs and highlight the unique student experience for undergraduate students on our
          campus.
        </p>

        <p className="about-text">
          Please see more details if you are interested in partnering with us:
        </p>

        <ul className="about-list">
          <li>
            You may{' '}
            <a
              href="https://i2g.ucmerced.edu/partnership"
              target="_blank"
              rel="noopener noreferrer"
            >
              sponsor
            </a>{' '}
            the program and events.
          </li>
          <li>
            You may{' '}
            <Link to="/project-submission">propose a project</Link> that can be evaluated for fit in
            Engineering Capstone, Software Engineering Capstone, or Service Learning, or an
            internship, or potentially collaborative research with Faculty at UC Merced.
          </li>
          <li>
            You may search all <Link to="/past-projects">past projects</Link> of Innovate to Grow
            since 2012, and <Link to="/current-projects">current student teams and projects</Link> in this
            semester Innovate to Grow classes and event.
          </li>
          <li>
            You may sign up to judge or attend the{' '}
            <a
              href="https://i2g.ucmerced.edu/event"
              target="_blank"
              rel="noopener noreferrer"
            >
              next Innovate to Grow event
            </a>
            .
          </li>
        </ul>

        <p className="about-text">
          For any questions or comments, please send us an email to:{' '}
          <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>
        </p>
      </div>
    </div>
  );
};
