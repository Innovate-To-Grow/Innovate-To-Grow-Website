import {Navigate, useLocation} from 'react-router-dom';

// Preserves ?token=... while forwarding old email links (/magic-login,
// /ticket-login) to /login-link.
export function LegacyLoginLinkRedirect() {
    const {search} = useLocation();
    return <Navigate to={{pathname: '/login-link', search}} replace/>;
}
