import {Link} from 'react-router-dom';
import './AcknowledgementPage.css';

export const AcknowledgementPage = () => {
  return (
    <div className="ack-page">
      <h1 className="ack-page-title">Partners &amp; Sponsors</h1>

      <p className="ack-page-lead">
        The Innovate to Grow program thrives thanks to the generous support of our partners and
        sponsors. Their commitment to engineering education and student innovation makes this
        program possible.
      </p>

      <p className="ack-page-text">
        We extend our sincere gratitude to all organizations and individuals who contribute to
        Innovate to Grow through project sponsorship, financial support, mentorship, and judging.
        Your involvement directly impacts the educational experience of UC Merced students and
        helps prepare the next generation of engineers and innovators.
      </p>

      <section className="ack-page-section">
        <h2 className="ack-page-section-title">Our Sponsors</h2>
        <div className="ack-page-placeholder">
          <p className="ack-page-text">
            Sponsor logos and acknowledgements will be updated for each event.
          </p>
        </div>
      </section>

      <section className="ack-page-section">
        <h2 className="ack-page-section-title">Become a Sponsor</h2>
        <p className="ack-page-text">
          Interested in supporting the Innovate to Grow program? Learn more about sponsorship
          opportunities and how your organization can get involved.
        </p>
        <p className="ack-page-text">
          <Link to="/sponsorship" className="ack-page-link">
            View Sponsorship Information
          </Link>
        </p>
        <p className="ack-page-text">
          For questions about sponsorship, please contact us at{' '}
          <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
        </p>
      </section>
    </div>
  );
};
