import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { verifyEmail } from '../services/api';
import './EmailVerificationPage.css';

export const EmailVerificationPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token');

  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [verifiedEmail, setVerifiedEmail] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setError('No verification token provided.');
      return;
    }

    const verify = async () => {
      setLoading(true);
      try {
        const response = await verifyEmail({ token });
        setSuccess(true);
        setVerifiedEmail(response.email);
      } catch (err: any) {
        if (err.response?.data?.error) {
          setError(err.response.data.error);
        } else if (err.response?.data) {
          setError(typeof err.response.data === 'string' 
            ? err.response.data 
            : 'Verification failed. Please try again.');
        } else {
          setError('An error occurred during verification. Please try again.');
        }
      } finally {
        setLoading(false);
      }
    };

    verify();
  }, [token]);

  if (loading) {
    return (
      <div className="verification-container">
        <div className="verification-status">
          <h1>Verifying Email...</h1>
          <p>Please wait while we verify your email address.</p>
        </div>
      </div>
    );
  }

  if (success) {
    return (
      <div className="verification-container">
        <div className="verification-success">
          <h1>Email Verified Successfully!</h1>
          <p>Your email address {verifiedEmail} has been verified.</p>
          <p>You can now use all features of your account.</p>
          <button onClick={() => navigate('/')} className="home-button">
            Go to Homepage
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="verification-container">
      <div className="verification-error">
        <h1>Verification Failed</h1>
        <p>{error || 'Unable to verify your email address.'}</p>
        <p>The verification link may have expired or is invalid.</p>
        <button onClick={() => navigate('/signup')} className="signup-button">
          Go to Signup
        </button>
      </div>
    </div>
  );
};
