import './MaintenanceMode.css';

export const MaintenanceMode = () => {
  return (
    <div className="maintenance-container">
      <div className="maintenance-shell">
        <div className="maintenance-main">
          <main className="maintenance-content">
          <div className="maintenance-card">
            <div className="maintenance-hero">
              <div className="maintenance-title-row">
                  <img 
                    src="/static/images/ucmlogo.png" 
                    alt="UC Merced" 
                    className="maintenance-ucm-logo"
                  />
              </div>
            </div>

            <section className="maintenance-status-card" aria-label="System status">
              <div className="status-item">
                <div className="status-logo-wrapper" aria-hidden="true">
                  <img
                    className="status-logo status-logo-browser"
                    src="https://upload.wikimedia.org/wikipedia/commons/8/87/Google_Chrome_icon_%282011%29.png"
                    alt=""
                  />
                </div>
                <div className="status-text">
                  <div className="status-title">Your Browser</div>
                  <div className="status-subtitle status-subtitle-ok">Normal</div>
                </div>
              </div>

              <div className="status-item">
                <div className="status-logo-wrapper" aria-hidden="true">
                  <img
                    className="status-logo status-logo-aws"
                    src="https://upload.wikimedia.org/wikipedia/commons/9/93/Amazon_Web_Services_Logo.svg"
                    alt=""
                  />
                </div>
                <div className="status-text">
                  <div className="status-title">Amazon Web Services</div>
                  <div className="status-subtitle status-subtitle-alert">Always down</div>
                </div>
              </div>

              <div className="status-item">
                <div className="status-logo-wrapper" aria-hidden="true">
                  <img
                    className="status-logo status-logo-backend"
                    src="/static/images/i2glogo.png"
                    alt=""
                  />
                </div>
                <div className="status-text">
                  <div className="status-title">Hongzhe's Backend Code</div>
                  <div className="status-subtitle status-subtitle-ok">Always working</div>
                </div>
              </div>
            </section>

            <section className="maintenance-info" aria-label="Maintenance details">
              <div className="info-block">
                <h2>What happened?</h2>
                <p>We are performing scheduled maintenance on this service.</p>
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
          <p className="maintenance-copyright">© {new Date().getFullYear()} The Regents of the University of California</p>
        </footer>
      </div>
    </div>
  );
};
