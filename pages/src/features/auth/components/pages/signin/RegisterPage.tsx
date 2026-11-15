import '@/features/auth/components/shared/linkLandingPages.css';
import {useEffect} from 'react';
import {useNavigate} from 'react-router';
import {getRegisterLinkPath, getSafeInternalRedirectPath} from '@/features/auth/api';

const SIGN_IN_PATH = '/login';

/**
 * `/register`: the short link (and QR code) on flyers and slides. It goes where
 * staff pointed it (Mail → SMS Settings), by default the sign-in page, which
 * takes an email address or a phone number and creates the account. Anything
 * that is not a safe page on this site, or no answer, leads to the sign-in page.
 */
export const RegisterPage = () => {
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;
    const go = (path: string | null) => {
      if (cancelled) return;
      const safe = getSafeInternalRedirectPath(path);
      const loops = safe?.split('?')[0].replace(/\/+$/, '') === '/register';
      navigate(safe && !loops ? safe : SIGN_IN_PATH, {replace: true});
    };
    getRegisterLinkPath().then(go, () => go(null));
    return () => {
      cancelled = true;
    };
  }, [navigate]);

  return (
    <div className="magic-login-page">
      <p className="magic-login-status" role="status">Opening registration...</p>
    </div>
  );
};
