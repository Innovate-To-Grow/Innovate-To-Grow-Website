import { Link } from 'react-router-dom';
import './FaqPage.css';

export const FaqPage = () => {
  return (
    <div className="faq-page">
      <h1 className="faq-page-title">Frequently Asked Questions</h1>

      <div className="faq-content">
        <h2 className="faq-question">What is a Capstone Project?</h2>
        <p className="faq-text">
          <strong>Engineering Capstone</strong> (formerly known as Innovation Design Clinic) is a
          senior-year, year-long design experience for engineering majors. See more at{' '}
          <Link to="/engineering-capstone">Engineering Capstone</Link>.
        </p>
        <p className="faq-text">
          <strong>Software Capstone</strong> (formerly known as Mobile App Challenge) is a
          semester-long software engineering project course for computer science students. See more
          at <Link to="/software-capstone">Software Capstone</Link>.
        </p>
        <p className="faq-text">
          A "Capstone" is a culminating academic experience in which students apply the knowledge
          and skills they have acquired throughout their coursework to a real-world project. The
          School of Engineering at UC Merced encompasses the following disciplines: Bioengineering,
          Civil &amp; Environmental Engineering, Computer Science &amp; Engineering, Materials
          Science &amp; Engineering, and Mechanical Engineering.
        </p>

        <h2 className="faq-question">What is Innovate to Grow?</h2>
        <p className="faq-text">
          Innovate to Grow (I2G) is a unique "experiential learning" program at the UC Merced
          School of Engineering. It engages external partner organizations with teams of students who
          design systems to solve complex, real-world problems. At the end of each semester, the work
          completed by the student teams culminates in the Innovate to Grow event, which features
          student-led research presentations and highlights their project outcomes.
        </p>

        <h2 className="faq-question">How are the Capstone projects proposed?</h2>
        <p className="faq-text">
          A proposal is submitted with the following format:
        </p>
        <ul className="faq-list">
          <li><strong>Organization:</strong> Name of the sponsoring organization</li>
          <li><strong>Mentor(s):</strong> Name and contact information of the project mentor(s)</li>
          <li><strong>Project Title:</strong> A descriptive title for the project</li>
          <li><strong>Background:</strong> Context and background information</li>
          <li><strong>Problem:</strong> The problem or challenge to be addressed</li>
          <li><strong>Objective:</strong> The desired outcome or deliverable</li>
        </ul>
        <p className="faq-text">
          You may <Link to="/project-submission">propose a project</Link>, view{' '}
          <Link to="/sample-proposals">sample proposals</Link>, or search{' '}
          <Link to="/past-projects">past projects</Link>.
        </p>

        <h2 className="faq-question">What type of projects are applicable to Capstone?</h2>
        <p className="faq-text">
          <strong>Engineering Capstone</strong> projects need to involve a significant design and
          prototyping component. These projects span two semesters (a full academic year).
        </p>
        <p className="faq-text">
          <strong>Software Capstone</strong> projects need to involve a significant software
          engineering component. These projects are completed within one semester.
        </p>

        <h2 className="faq-question">When is the deadline to submit project proposals?</h2>
        <p className="faq-text">
          The deadline for projects starting in the <strong>Spring</strong> semester is{' '}
          <strong>December 31</strong>. The deadline for projects starting in the{' '}
          <strong>Fall</strong> semester is <strong>July 31</strong>.
        </p>

        <h2 className="faq-question">How are the teams and projects selected?</h2>
        <p className="faq-text">
          Faculty compiles the list of available projects and presents them to students. Students
          then select their preferred projects through a web-based poll. Teams are formed based on
          student preferences and project requirements.
        </p>

        <h2 className="faq-question">How many projects can an organization submit?</h2>
        <p className="faq-text">
          There is no hard limit on the number of projects an organization can submit. We welcome
          multiple proposals and will evaluate each for fit within the program.
        </p>

        <h2 className="faq-question">
          Is there a time commitment for the sponsoring organization?
        </h2>
        <p className="faq-text">
          Yes. Each project requires at least one designated mentor from the sponsoring organization.
          Mentors are expected to interact with their student team on a weekly or bi-weekly basis to
          provide guidance, feedback, and domain expertise.
        </p>

        <h2 className="faq-question">
          Is there a financial commitment for the sponsoring organization?
        </h2>
        <p className="faq-text">
          Financial sponsorship is not mandatory. However, donations are welcome and help support the
          program, student travel, prototyping materials, and the Innovate to Grow event. If you are
          interested in sponsoring, please visit our{' '}
          <Link to="/partnership">partnership page</Link>.
        </p>

        <h2 className="faq-question">What is the timeline?</h2>
        <p className="faq-text">
          <strong>Engineering Capstone</strong> has two cycles of year-long projects:
        </p>
        <ul className="faq-list">
          <li>
            <strong>CAP-1xx (Fall + Spring):</strong> Projects begin in August and conclude in May of
            the following year.
          </li>
          <li>
            <strong>CAP-2xx (Spring + Fall):</strong> Projects begin in January and conclude in
            December of the same year.
          </li>
        </ul>
        <p className="faq-text">
          <strong>Software Capstone</strong> has two cycles of semester-long projects:
        </p>
        <ul className="faq-list">
          <li>
            <strong>CSE-3xx (Fall):</strong> Projects run from August to December.
          </li>
          <li>
            <strong>CSE-3xx (Spring):</strong> Projects run from January to May.
          </li>
        </ul>

        <h2 className="faq-question">
          What are the roles and expectations of judging at I2G?
        </h2>
        <p className="faq-text">
          Judges at Innovate to Grow events are expected to:
        </p>
        <ul className="faq-list">
          <li>Review student project presentations and posters</li>
          <li>Evaluate the technical merit, creativity, and feasibility of each project</li>
          <li>Provide constructive feedback to student teams</li>
          <li>Score projects based on the provided rubric</li>
          <li>Participate in deliberation to select award recipients</li>
        </ul>

        <h2 className="faq-question">How is Capstone related to Innovate to Grow?</h2>
        <p className="faq-text">
          Engineering Capstone and Software Capstone are academic classes offered by the School of
          Engineering at UC Merced. Innovate to Grow is the broader program and bi-annual showcase
          event where student teams present the results of their capstone projects, alongside other
          experiential learning classes. In short, the Capstone classes are the academic coursework,
          while Innovate to Grow is the program and event that highlights and celebrates student
          work.
        </p>
      </div>
    </div>
  );
};
