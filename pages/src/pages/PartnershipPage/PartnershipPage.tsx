import { Link } from 'react-router-dom';
import './PartnershipPage.css';

export const PartnershipPage = () => {
  return (
    <div className="partnership-page">
      <h1 className="partnership-page-title">Partnership Opportunities</h1>
      <h2 className="partnership-section-title">Thank you for your Support!</h2>
      <p className="partnership-text">
        If you would like to be a part of the exciting programming offered by the School of Engineering
        (the Innovate to Grow event or our "experiential learning" Engineering Capstone, Software
        Engineering Capstone, and Engineering Service Learning classes), consider participating in one of
        the following ways listed below:
      </p>
      <ul className="partnership-list">
        <li><Link to="/project-submission">Propose / mentor a project</Link></li>
        <li><Link to="/judges">Sign up to Judge</Link></li>
        <li><Link to="/sponsorship">Sponsor the program or event</Link></li>
        <li><Link to="/faqs">FAQs</Link></li>
      </ul>
      <p className="partnership-text">
        For further information or if you have any questions, please contact us at email{' '}
        <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
      </p>
    </div>
  );
};
