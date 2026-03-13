import { Link } from 'react-router-dom';
import './SponsorshipPage.css';

export const SponsorshipPage = () => {
  return (
    <div className="sponsorship-page">
      <h1 className="sponsorship-page-title">Sponsorship Opportunities</h1>

      <h2 className="sponsorship-section-title">Why sponsor Innovate to Grow and the School of Engineering?</h2>
      <p className="sponsorship-text">
        The School of Engineering provides an intellectual environment for research and education that
        makes UC Merced a magnet for innovation. Together, students create transformational impacts on the
        world we live in.
      </p>
      <p className="sponsorship-text">
        Your donation improves the School of Engineering experiential learning classes and their projects,
        and the bi-annual Innovate to Grow event and student showcase. Gifts to the School of Engineering
        also help support critical areas that ensure a strong foundation for building excellence in our
        education programs, cross-functional research, and outstanding partnerships and service. Our goal
        is to have enough award funding to help the very best students accelerate toward a successful
        career and bright future.
      </p>

      <h2 className="sponsorship-section-title">Recognition</h2>
      <p className="sponsorship-text">
        UC Merced is honored to acknowledge sponsors for their commitment to and partnership with our
        programs. Recognition can include acknowledgment in publicity materials, flyers and posters, email
        announcements, web pages, media releases and publications of Innovate to Grow.
      </p>

      <h2 className="sponsorship-section-title">How to Support</h2>
      <p className="sponsorship-text">
        If you would like to contribute as a sponsor of an Innovate to Grow project, or as an affiliate
        to the Innovate to Grow event, please contact us at{' '}
        <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
      </p>
      <p className="sponsorship-text">
        General{' '}
        <a href="https://securelb.imodules.com/s/1650/index.aspx?sid=1650&gid=1&pgid=474&dids=12&bledit=1&appealcode=2014-15%20I2G" target="_blank" rel="noopener noreferrer">
          Gifts
        </a>{' '}
        to the school also help support critical areas that ensure a strong foundation for building
        excellence in our education programs, cross-functional research, and outstanding partnerships and
        service. Our goal is to have enough award funding to help the very best students accelerate toward
        a successful career and bright future.
      </p>

      <h2 className="sponsorship-section-title">Past Sponsors</h2>
      <p className="sponsorship-text"><Link to="/acknowledgement">2020 Sponsors</Link></p>
      <p className="sponsorship-text"><Link to="/acknowledgement">2019 Sponsors</Link></p>
      <p className="sponsorship-text">
        <a href="https://issuu.com/ucmsoe/docs/uc_merced_-_program_innovate_to_gro/14" target="_blank" rel="noopener noreferrer">2018 Sponsors</a>
      </p>
      <p className="sponsorship-text">
        <a href="https://issuu.com/ucmsoe/docs/innovate2growprogram_2017_final/17" target="_blank" rel="noopener noreferrer">2017 Sponsors</a>
      </p>
      <p className="sponsorship-text">
        <a href="https://ucmerced.box.com/v/innovatetogrow-sponsors-2016" target="_blank" rel="noopener noreferrer">2016 Sponsors</a>
      </p>
      <p className="sponsorship-text"><Link to="/sponsors/2015">2015 Sponsors</Link></p>
      <p className="sponsorship-text"><Link to="/sponsors/2014">2014 Sponsors</Link></p>

      <p className="sponsorship-text">
        For further information or if you have any questions, please contact us at{' '}
        <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
      </p>
    </div>
  );
};
