import './MaintenanceMode.css';
import { useState, type FormEvent } from 'react';
import { Icon } from '@/components/Icon/Icon';

interface MaintenanceModeProps {
  message?: string;
  maintenance?: boolean;
  onBypass?: (password: string) => Promise<boolean>;
}

/** The staff bypass state; kept by the page so the typed password survives hiding the form. */
const useBypassForm = (onBypass: MaintenanceModeProps['onBypass']) => {
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

  return { password, setPassword, error, loading, handleSubmit };
};

/** The staff bypass: a password that, when accepted, lets this browser past maintenance. */
const BypassForm = ({ form }: { form: ReturnType<typeof useBypassForm> }) => {
  const { password, setPassword, error, loading, handleSubmit } = form;
  return (
    <form className="bypass-form" onSubmit={handleSubmit}>
      <label className="bypass-label" htmlFor="maintenance-bypass-password">
        Bypass password
      </label>
      <div className="bypass-row">
        <input
          id="maintenance-bypass-password"
          type="password"
          className="bypass-input"
          placeholder="Enter bypass password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoFocus
          disabled={loading}
        />
        <button type="submit" className="bypass-submit" disabled={loading || !password.trim()}>
          {loading ? 'Verifying...' : 'Enter'}
        </button>
      </div>
      {error && <p className="bypass-error" role="alert">{error}</p>}
    </form>
  );
};

/**
 * Full-screen maintenance page. It replaces the whole app (menu, footer and the
 * layout data may be unavailable), so the UC Merced card and footer are styled
 * entirely by the frontend bundle.
 */
export const MaintenanceMode = ({ message, maintenance, onBypass }: MaintenanceModeProps) => {
  const displayMessage = message || 'The system is currently temporarily down for maintenance. We apologize for the inconvenience and appreciate your patience.';

  const [showForm, setShowForm] = useState(false);
  const bypassForm = useBypassForm(onBypass);

  const canBypass = Boolean(maintenance && onBypass);

  return (
    <div className="maintenance-container">
      <div className="maintenance-shell">
        {/* The shell already supplies <main id="main">, so this must not add another main. */}
        <div className="maintenance-content">
          <div className="maintenance-card">
            <div className="maintenance-title-row">
              <img src="/assets/images/ucmlogo.png" alt="UC Merced" className="maintenance-ucm-logo" width={138} height={34} />
              <div className="maintenance-gear" aria-hidden="true">
                <Icon name="cog" />
              </div>
            </div>

            <div className="maintenance-alert">
              <div className="maintenance-alert-icon" aria-hidden="true">
                <Icon name="exclamation-triangle" />
              </div>
              <div className="maintenance-alert-content">
                <h1 className="maintenance-title">Service Unavailable</h1>
                <p className="maintenance-lead" role="status">{displayMessage}</p>
              </div>
            </div>

            <section className="maintenance-info" aria-label="Maintenance details">
              <div className="maintenance-info-block">
                <h2>What happened?</h2>
                <p>We are performing maintenance on this service.</p>
              </div>
              <div className="maintenance-info-block">
                <h2>What can I do?</h2>
                <p>Please try again in a few minutes. This page will refresh automatically.</p>
              </div>
            </section>
          </div>
        </div>

        <footer className="maintenance-footer">
          <nav className="maintenance-footer-links" aria-label="University links">
            <a href="https://www.ucmerced.edu" target="_blank" rel="noopener noreferrer">UC Merced</a>
            <span className="maintenance-footer-divider" aria-hidden="true">|</span>
            <a href="https://engineering.ucmerced.edu" target="_blank" rel="noopener noreferrer">School of Engineering</a>
            {canBypass && (
              <>
                <span className="maintenance-footer-divider" aria-hidden="true">|</span>
                <button
                  type="button"
                  className="bypass-toggle-link"
                  aria-expanded={showForm}
                  onClick={() => setShowForm(!showForm)}
                >
                  Bypass with Password
                </button>
              </>
            )}
          </nav>

          {showForm && canBypass ? <BypassForm form={bypassForm} /> : null}

          <p className="maintenance-copyright">&copy; {new Date().getFullYear()} The Regents of the University of California</p>
        </footer>
      </div>
    </div>
  );
};
