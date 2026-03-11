import { Link } from 'react-router-dom';
import './SoftwareCapstonePage.css';

export const SoftwareCapstonePage = () => {
  return (
    <div className="capstone-page">
      <h1 className="capstone-page-title">Software Engineering Capstone</h1>

      <div className="capstone-content">
        <img
          src="/assets/about/software_engineering_capstone.png"
          alt="Software Engineering Capstone"
          className="capstone-hero-image"
        />

        <p className="capstone-text">
          Software Engineering Capstone (formerly known as Mobile App Challenge) encourages UC Merced
          students to develop innovative software applications for today's industry and societal
          needs, and currently involves students in the Software Engineering CSE 120 class.
        </p>

        <p className="capstone-text">
          Partner organizations and companies provide problems and software projects, and play a
          vital role by helping the students gain real-world experience and skills that will carry
          them into their future careers, while the partners also get solutions to their own software
          and data management needs.
        </p>

        <p className="capstone-text">
          The Software Capstone provides UC Merced's Computer Science seniors opportunities to learn
          and contribute in teams that include practicing professionals from partner and sponsoring
          organizations.
        </p>

        <p className="capstone-text">
          The Software teams focus on design and development projects chosen based on their potential
          for significant near-term effects on communities, organizations and/or industries in the
          region. The commitment of the teams and partners, combined with the richness and intensity
          of the Innovate to Grow competition, greatly enhances the software engineering experience.
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
          processes and business systems become more complex, UC Merced computer science and
          engineering students are becoming an essential part of the industry and are contributing to
          regional economic, social and cultural growth.
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
