import './MaintenanceMode.css';

interface MaintenanceModeProps {
  message?: string;
}

export const MaintenanceMode = ({ message }: MaintenanceModeProps) => {
  const displayMessage = message || 'The system is currently temporarily down for maintenance. We apologize for the inconvenience and appreciate your patience.';

  return (
    <div className="maintenance-container">
      <div className="maintenance-shell">
        <div className="maintenance-main">
          <main className="maintenance-content">
          <div className="maintenance-card">
            <div className="maintenance-hero">
              <div className="maintenance-title-row">
                  <img
                    src="/assets/images/ucmlogo.png"
                    alt="UC Merced"
                    className="maintenance-ucm-logo"
                  />
                  <div className="maintenance-gear">
                    <i className="fa fa-cog" aria-hidden="true"></i>
                  </div>
              </div>
            </div>

            <div className="maintenance-alert">
              <div className="maintenance-alert-icon">
                <i className="fa fa-exclamation-triangle" aria-hidden="true"></i>
              </div>
              <div className="maintenance-alert-content">
                <h3>Service Unavailable</h3>
                <p>{displayMessage}</p>
              </div>
            </div>

            <section className="maintenance-info" aria-label="Maintenance details">
              <div className="info-block">
                <h2>What happened?</h2>
                <p>We are performing maintenance on this service.</p>
              </div>
              <div className="info-block">
                <h2>What can I do?</h2>
                <p>Please try again in a few minutes. This page will refresh automatically.</p>
              </div>
            </section>
          </div>
        </main>
        </div>

        <footer className="maintenance-footer">
          <div className="maintenance-footer-links">
            <a href="https://www.ucmerced.edu" target="_blank" rel="noopener noreferrer">UC Merced</a>
            <span className="footer-divider">|</span>
            <a href="https://engineering.ucmerced.edu" target="_blank" rel="noopener noreferrer">School of Engineering</a>
          </div>
          <p className="maintenance-copyright">&copy; {new Date().getFullYear()} The Regents of the University of California</p>
        </footer>
      </div>
    </div>
  );
};
