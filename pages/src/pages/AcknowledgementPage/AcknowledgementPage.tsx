import {useEffect, useState} from 'react';
import {Link} from 'react-router-dom';
import {fetchSponsors, type SponsorYear} from '../../features/sponsors/api';
import './AcknowledgementPage.css';

export const AcknowledgementPage = () => {
  const [sponsorYears, setSponsorYears] = useState<SponsorYear[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSponsors()
      .then(setSponsorYears)
      .catch(() => setSponsorYears([]))
      .finally(() => setLoading(false));
  }, []);

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

      {loading ? (
        <div className="ack-page-loading">Loading sponsors...</div>
      ) : sponsorYears.length > 0 ? (
        sponsorYears.map(({year, sponsors}) => (
          <section key={year} className="ack-page-section">
            <h2 className="ack-page-section-title">{year} Sponsors</h2>
            <div className="ack-sponsor-grid">
              {sponsors.map((sponsor) => (
                <a
                  key={sponsor.id}
                  href={sponsor.website || undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={`ack-sponsor-card${sponsor.website ? '' : ' no-link'}`}
                >
                  {sponsor.logo ? (
                    <img
                      src={sponsor.logo}
                      alt={sponsor.name}
                      className="ack-sponsor-logo"
                      loading="lazy"
                    />
                  ) : (
                    <div className="ack-sponsor-logo-placeholder">{sponsor.name[0]}</div>
                  )}
                  <span className="ack-sponsor-name">{sponsor.name}</span>
                </a>
              ))}
            </div>
          </section>
        ))
      ) : (
        <section className="ack-page-section">
          <h2 className="ack-page-section-title">Our Sponsors</h2>
          <div className="ack-page-placeholder">
            <p className="ack-page-text">
              Sponsor logos and acknowledgements will be updated for each event.
            </p>
          </div>
        </section>
      )}

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
