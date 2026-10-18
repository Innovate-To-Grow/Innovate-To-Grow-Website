import { useState, type FormEvent } from 'react';

interface MaintenanceModeProps {
  message?: string;
  maintenance?: boolean;
  onBypass?: (password: string) => Promise<boolean>;
}

/**
 * Full-screen maintenance page. It replaces the whole app (menu, footer and the
 * layout data may be unavailable), so it carries its own UC Merced chrome: the
 * navy bar with the gold rule, the site-name band, and a footer.
 */
export const MaintenanceMode = ({ message, maintenance, onBypass }: MaintenanceModeProps) => {
  const displayMessage = message || 'The system is currently temporarily down for maintenance. We apologize for the inconvenience and appreciate your patience.';

  const [showForm, setShowForm] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!password.trim() || !onBypass) return;

    setError('');
    setLoading(true);
    try {
      const success = await onBypass(password);
      if (!success) {
        setError('Incorrect password.');
      }
    } catch {
      setError('Failed to verify. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const canBypass = Boolean(maintenance && onBypass);

  return (
    <div className="maintenance-container">
      <header className="maintenance-bar">
        <div className="maintenance-bar-inner">
          <a href="https://www.ucmerced.edu" className="maintenance-ucm-link">
            <img src="/assets/images/ucmlogo.png" alt="UC Merced" className="maintenance-ucm-logo" width={138} height={34} />
          </a>
        </div>
      </header>

      <div className="maintenance-band">
        <div className="maintenance-band-inner">
          <p className="maintenance-site-name">Innovate To Grow</p>
          <p className="maintenance-site-school">School of Engineering</p>
        </div>
      </div>

      {/* A div, not <main>: this page renders inside the shell's own <main id="main">, and
          a second main landmark nested in it is an accessibility error. */}
      <div className="maintenance-content">
        <h1 className="maintenance-title">Service Unavailable</h1>
        <p className="maintenance-meta">Scheduled maintenance</p>
        <p className="maintenance-lead" role="status">{displayMessage}</p>

        <section className="maintenance-info" aria-label="Maintenance details">
          <div className="itg-panel maintenance-info-block">
            <h2>What happened?</h2>
            <p>We are performing maintenance on this service.</p>
          </div>
          <div className="itg-panel maintenance-info-block">
            <h2>What can I do?</h2>
            <p>Please try again in a few minutes. This page will refresh automatically.</p>
          </div>
        </section>
      </div>

      <footer className="maintenance-footer">
        <div className="maintenance-footer-inner">
          <nav className="maintenance-footer-links" aria-label="University links">
            <a href="https://www.ucmerced.edu" target="_blank" rel="noopener noreferrer">UC Merced</a>
            <a href="https://engineering.ucmerced.edu" target="_blank" rel="noopener noreferrer">School of Engineering</a>
            {canBypass && (
              <button
                type="button"
                className="itg-btn itg-btn-text bypass-toggle-link"
                aria-expanded={showForm}
                onClick={() => setShowForm(!showForm)}
              >
                Bypass with Password
              </button>
            )}
          </nav>

          {showForm && canBypass && (
            <form className="bypass-form" onSubmit={handleSubmit}>
              <label className="itg-label bypass-label" htmlFor="maintenance-bypass-password">
                Bypass password
              </label>
              <div className="bypass-row">
                <input
                  id="maintenance-bypass-password"
                  type="password"
                  className="itg-input bypass-input"
                  placeholder="Enter bypass password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoFocus
                  disabled={loading}
                />
                <button type="submit" className="itg-btn itg-btn-primary bypass-submit" disabled={loading || !password.trim()}>
                  {loading ? 'Verifying...' : 'Enter'}
                </button>
              </div>
              {error && <p className="itg-error bypass-error" role="alert">{error}</p>}
            </form>
          )}
        </div>

        <div className="maintenance-footer-bottom">
          <p className="maintenance-copyright">&copy; {new Date().getFullYear()} The Regents of the University of California</p>
        </div>
      </footer>
    </div>
  );
};
