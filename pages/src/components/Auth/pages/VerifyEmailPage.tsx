import { useEffect, useState, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import '../Auth.css';

export const VerifyEmailPage = () => {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();
  const { verifyEmail, error } = useAuth();
  // Initialize status based on whether token exists
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>(
    token ? 'verifying' : 'error'
  );
  const hasVerified = useRef(false);

  useEffect(() => {
    if (!token || hasVerified.current) {
      return;
    }

    hasVerified.current = true;

    const verify = async () => {
      try {
        await verifyEmail(token);
        setStatus('success');
        // Redirect to home after 2 seconds
        setTimeout(() => navigate('/'), 2000);
      } catch {
        setStatus('error');
      }
    };

    verify();
  }, [token, verifyEmail, navigate]);

  return (
    <div className="verify-email-page">
      <div className="verify-email-card">
        {status === 'verifying' && (
          <>
            <div className="verify-email-icon verifying">
              <i className="fa fa-spinner fa-spin" />
            </div>
            <h1 className="verify-email-title">Verifying your email...</h1>
            <p className="verify-email-text">Please wait while we verify your email address.</p>
          </>
        )}

        {status === 'success' && (
          <>
            <div className="verify-email-icon success">
              <i className="fa fa-check-circle" />
            </div>
            <h1 className="verify-email-title">Email Verified!</h1>
            <p className="verify-email-text">
              Your email has been verified successfully. Redirecting you to the homepage...
            </p>
          </>
        )}

        {status === 'error' && (
          <>
            <div className="verify-email-icon error">
              <i className="fa fa-times-circle" />
            </div>
            <h1 className="verify-email-title">Verification Failed</h1>
            <p className="verify-email-text">
              {error || 'The verification link is invalid or has expired.'}
            </p>
            <button
              type="button"
              className="verify-email-button"
              onClick={() => navigate('/')}
            >
              Go to Homepage
            </button>
          </>
        )}
      </div>

      <style>{`
        .verify-email-page {
          min-height: 60vh;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 2rem;
        }

        .verify-email-card {
          background: #fff;
          border-radius: 12px;
          box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
          padding: 3rem;
          text-align: center;
          max-width: 400px;
          width: 100%;
        }

        .verify-email-icon {
          font-size: 4rem;
          margin-bottom: 1.5rem;
        }

        .verify-email-icon.verifying {
          color: #003366;
        }

        .verify-email-icon.success {
          color: #22c55e;
        }

        .verify-email-icon.error {
          color: #dc2626;
        }

        .verify-email-title {
          font-size: 1.5rem;
          font-weight: 600;
          color: #1f2937;
          margin: 0 0 0.75rem 0;
        }

        .verify-email-text {
          color: #6b7280;
          font-size: 0.95rem;
          line-height: 1.5;
          margin: 0 0 1.5rem 0;
        }

        .verify-email-button {
          background: #003366;
          color: #fff;
          border: none;
          padding: 0.875rem 2rem;
          border-radius: 8px;
          font-size: 1rem;
          font-weight: 600;
          cursor: pointer;
          transition: background-color 0.15s;
        }

        .verify-email-button:hover {
          background: #00254d;
        }
      `}</style>
    </div>
  );
};
