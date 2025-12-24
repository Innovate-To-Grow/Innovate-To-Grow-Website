import './MaintenanceMode.css';

export const MaintenanceMode = () => {
  return (
    <div className="maintenance-container">
      {/* Decorative Background Elements */}
      <div className="maintenance-bg-pattern"></div>
      
      <div className="maintenance-content">
        {/* UC Merced Logo */}
        <div className="maintenance-logo-group">
          <img 
            src="https://innovatetogrow.ucmerced.edu/sites/all/themes/UCMerced/ucmlogo.png" 
            alt="UC Merced" 
            className="maintenance-ucm-logo"
          />
          <div className="maintenance-logo-divider"></div>
          <img 
            src="/static/images/I2G-fullname-low.png" 
            alt="Innovate To Grow" 
            className="maintenance-i2g-logo"
          />
        </div>

        {/* Maintenance Icon */}
        <div className="maintenance-icon">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="12" cy="12" r="3" />
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
          </svg>
        </div>
        
        <h1 className="maintenance-title">System Maintenance</h1>
        
        <div className="maintenance-message">
          <p>
            Our team is currently performing scheduled maintenance to improve your experience.
          </p>
          <p className="maintenance-message-secondary">
            Thank you for your patience. The page will automatically refresh when service is restored.
          </p>
        </div>
      </div>

      <div className="maintenance-footer">
        <div className="maintenance-footer-links">
          <a href="https://www.ucmerced.edu" target="_blank" rel="noopener noreferrer">UC Merced</a>
          <span className="footer-divider">|</span>
          <a href="https://engineering.ucmerced.edu" target="_blank" rel="noopener noreferrer">School of Engineering</a>
        </div>
        <p className="maintenance-copyright">© {new Date().getFullYear()} The Regents of the University of California</p>
      </div>
    </div>
  );
};
