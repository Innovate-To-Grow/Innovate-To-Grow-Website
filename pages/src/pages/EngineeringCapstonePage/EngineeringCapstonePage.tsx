import { Link } from 'react-router-dom';
import './EngineeringCapstonePage.css';

export const EngineeringCapstonePage = () => {
  return (
    <div className="capstone-page">
      <h1 className="capstone-page-title">Engineering Capstone</h1>

      <div className="capstone-content">
        <img
          src="/assets/about/engineering_capstone.png"
          alt="Engineering Capstone"
          className="capstone-hero-image"
        />

        <p className="capstone-text">
          Engineering Capstone (also formerly known as Innovation Design Clinic) challenges UC
          Merced's engineering students to become entrepreneurs of their knowledge, skills and
          research applications.
        </p>

        <p className="capstone-text">
          Partner organizations and/or corporations play a vital role by helping the students gain
          real-world experience and skills that will carry them into their future careers, while the
          partners also get solutions to their own engineering needs.
        </p>

        <p className="capstone-text">
          Engineering Capstone provides UC Merced's graduating seniors opportunities to learn and
          contribute in teams that include practicing engineers and other professionals from partner
          and sponsoring organizations.
        </p>

        <p className="capstone-text">
          The Capstone teams focus on engineering design projects chosen based on their potential for
          significant near-term effects on communities, organizations and/or industries in the
          region. The commitment of the teams and partners, combined with the richness and intensity
          of the Innovate to Grow competition, greatly enhances the traditional capstone experience.
        </p>

        <p className="capstone-text">
          Through Capstone, classroom learning and students' research activity are coordinated with
          real-world design projects developed with partner organizations and industries to help share
          diverse approaches to designing and building solutions that fulfill client-based objectives.
        </p>

        <p className="capstone-text">
          Industry partners contribute sponsorships to the program's operation, and each project
          sponsor's involvement ranges from providing funds to the Innovate to Grow program, to
          engaging students in industry experiences.
        </p>

        <p className="capstone-text">
          We seek opportunities for students with partner organizations and industries to collaborate,
          discover solutions to common problems, create and streamline networking, and increase both
          radical and incremental innovation.
        </p>

        <p className="capstone-text">
          As industries and organizations become increasingly knowledge-based, and as products,
          processes and business systems become more complex, UC Merced engineering students are
          becoming an essential part of the industry and are contributing to regional economic, social
          and cultural growth.
        </p>

        <p className="capstone-text">
          You may search all <Link to="/past-projects">past projects</Link> of Innovate to Grow
          since 2012, and <Link to="/current-projects">current student teams and projects</Link>.
        </p>

        <p className="capstone-text">
          You may <Link to="/project-submission">propose a project</Link> that can be evaluated for
          fit in Engineering Capstone, Software Capstone, or an internship, or potentially
          collaborative research with Faculty at UC Merced.
        </p>
      </div>

    </div>
  );
};
