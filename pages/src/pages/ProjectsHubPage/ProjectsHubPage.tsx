import { Link } from 'react-router-dom';
import './ProjectsHubPage.css';

const projectLinks = [
  {
    to: '/past-projects',
    title: 'Past Projects',
    description:
      'Searchable database of Innovate to Grow projects since 2012.',
  },
  {
    to: '/current-projects',
    title: 'Current Projects',
    description:
      'Projects summaries, teams and students that are working on an Innovate to Grow project in the current Semester, showcasing in the upcoming I2G event.',
  },
  {
    to: '/project-submission',
    title: 'Project Submission',
    description:
      'Form to submit your project proposal, which will be evaluated for fit in Engineering Capstone, Software Capstone, or Service Learning, or an internship, or potentially collaborative research with Faculty at UC Merced. It starts with an idea that can be interactively refined.',
  },
  {
    to: '/sample-proposals',
    title: 'Samples of project proposals',
    description:
      'Examples of project proposals, as submitted in previous semesters by other organizations, for Engineering or Software problems, to give you an idea of how to prepare for your project submission.',
  },
];

export const ProjectsHubPage = () => {
  return (
    <div className="projects-hub-page">
      <h1 className="projects-hub-page-title">Projects</h1>

      <div className="projects-hub-list">
        {projectLinks.map((item) => (
          <p key={item.to} className="projects-hub-item">
            <Link to={item.to} className="projects-hub-link">{item.title}</Link>
            : {item.description}
          </p>
        ))}
      </div>

    </div>
  );
};
