import './ContactUsPage.css';

export const ContactUsPage = () => {
  return (
    <div className="contact-page">
      <h1 className="contact-page-title">Contact Us</h1>
      <p className="contact-text">
        For any questions, comments, or inquiries about the Innovate to Grow program, please reach out to us:
      </p>
      <p className="contact-text">
        <strong>Email:</strong>{' '}
        <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>
      </p>
      <p className="contact-text">
        <strong>Program:</strong> Innovate to Grow, School of Engineering, University of California, Merced
      </p>
    </div>
  );
};
