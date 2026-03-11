import { Link } from 'react-router-dom';
import './StudentsPage.css';

const studentLinks = [
  {
    to: '/student-agreement',
    title: 'I2G Project - Student Agreement',
    description:
      'The template of the agreement that a student must sign to participate in any project provided and sponsored by partner organizations. The agreement is digitally signed by acceptance in the survey to view and participate in projects at the beginning of the semester.',
  },
  {
    to: '/ferpa',
    title: 'FERPA Agreement',
    description:
      'The template of the agreement that a student must sign to participate in the Innovate to Grow event, allowing to record and distribute presentations and videos (media waiver).',
  },
  {
    to: '/video-preparation',
    title: 'Video Presentations',
    description:
      'Guidelines and instructions to prepare video presentations. Contains several general guidelines useful for any professional video presentation, particularly in engineering, with some details specific to Capstone and I2G.',
  },
  {
    to: '/event-preparation',
    title: 'I2G Event Preparation',
    description:
      'Information on I2G and instructions for students and teams to plan for it pre- during- and post-event.',
  },
  {
    to: '/purchasing-reimbursement',
    title: 'Purchasing / Travel / Expense Reimbursements',
    description:
      'Guidelines and forms for purchasing and travel reimbursement.',
  },
];

const externalLinks = [
  {
    href: 'https://ucmerced.az1.qualtrics.com/jfe/form/SV_e4L1PyHidYuThEW',
    title: 'Student Experience Survey',
    description:
      'Fill this survey for feedback and comments on the Capstone - I2G project, and event experience.',
  },
];

export const StudentsPage = () => {
  return (
    <div className="student-page">
      <h1 className="student-page-title">
        Students &amp; Teams - Resources for I2G Projects and Events
      </h1>

      <p className="student-text">
        This section contains information and guidelines for students and teams participating in:
      </p>
      <ul className="student-list">
        <li>An I2G project, such as Eng. Capstone and Software Engineering</li>
        <li>The I2G event and showcase</li>
      </ul>

      <div className="student-hub-list">
        {studentLinks.map((item) => (
          <p key={item.to} className="student-hub-item">
            <Link to={item.to} className="student-hub-link">{item.title}</Link>
            : {item.description}
          </p>
        ))}
        {externalLinks.map((item) => (
          <p key={item.href} className="student-hub-item">
            <a
              href={item.href}
              target="_blank"
              rel="noopener noreferrer"
              className="student-hub-link"
            >
              {item.title}
            </a>
            : {item.description}
          </p>
        ))}
      </div>

      <p className="student-text student-construction" style={{ marginTop: '2rem' }}>
        <strong>Student responsibilities</strong> — in construction...
      </p>
    </div>
  );
};
