import {Navigate, useLocation} from 'react-router';

// Callback credentials have already been captured and scrubbed before the
// browser router is created. Preserve any remaining, non-secret query/fragment
// state while forwarding old email links to the canonical route.
export function LegacyLoginLinkRedirect() {
    const {search, hash} = useLocation();
    return <Navigate to={{pathname: '/login-link', search, hash}} replace/>;
}
