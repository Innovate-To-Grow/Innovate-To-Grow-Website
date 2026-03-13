import { Link } from 'react-router-dom';
import './JudgesPage.css';

export const JudgesPage = () => {
  return (
    <div className="judges-page">
      <h1 className="judges-page-title">Judge</h1>

      <section className="judges-page-section">
        <h2 className="judges-section-header">Judge Role</h2>
        <ul className="judges-page-list">
          <li>No formal preparation is needed to be a judge.</li>
          <li>An engineering degree is not required.</li>
          <li>
            You contribute based on your experience and professional judgment.
          </li>
          <li>Judges fill out a questionnaire to evaluate each team.</li>
          <li>
            The questionnaire will be provided via email, QR code, and Zoom chat.
          </li>
        </ul>
      </section>

      <section className="judges-page-section">
        <h2 className="judges-section-header">How to Sign Up for Judging</h2>
        <p className="judges-page-text">
          To indicate interest in judging, check the box while registering. Select "Yes" in
          "Interested in Judging?" and you will be contacted by the I2G Team.
        </p>
        <p className="judges-page-text">
          You can also express interest by emailing{' '}
          <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
        </p>
      </section>

      <section className="judges-page-section">
        <h2 className="judges-section-header">Judging Preparation</h2>
        <p className="judges-page-text">Review the following links to prepare:</p>
        <ul className="judges-page-list">
          <li>
            <a
              href="https://youtu.be/aIQP17Vpbz4"
              target="_blank"
              rel="noopener noreferrer"
            >
              Video Instructions for I2G Judges
            </a>
          </li>
          <li>
            <Link to="/judging">Judging Forms</Link>
          </li>
          <li>
            <Link to="/event">Event Info and Schedule</Link>
          </li>
          <li>
            <Link to="/projects-teams">Projects &amp; Teams</Link>
          </li>
        </ul>
      </section>

      <section className="judges-page-section">
        <h2 className="judges-section-header">Event Day | Instructions for Judges</h2>

        <h3 className="judges-page-subtitle">IN PERSON</h3>
        <ul className="judges-page-list">
          <li>Judges are encouraged to join the Expo.</li>
          <li>
            Check the <Link to="/schedule">schedule</Link> for your assigned Room.
          </li>
          <li>Go to the room 10 minutes before your scheduled time.</li>
          <li>You are invited to the Award Ceremony.</li>
        </ul>

        <h3 className="judges-page-subtitle">ONLINE</h3>
        <ul className="judges-page-list">
          <li>
            Check the <Link to="/schedule">schedule</Link> for your assigned Zoom link.
          </li>
          <li>Go to the room 10 minutes before your scheduled time.</li>
          <li>
            Use the correct <Link to="/judging">Judging form</Link> for your track.
          </li>
          <li>Enter by clicking the link of your assigned track.</li>
        </ul>

        <p className="judges-page-text">
          For questions, email <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
        </p>
      </section>
    </div>
  );
};
