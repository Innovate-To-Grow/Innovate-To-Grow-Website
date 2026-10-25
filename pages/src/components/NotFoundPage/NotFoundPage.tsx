import './NotFoundPage.css';
import {Link} from 'react-router';
import {usePageTitle} from '@/hooks/usePageTitle';

export function NotFoundPage() {
  usePageTitle('Page Not Found');
  return (
    <section className="itg-empty-state not-found-page" aria-labelledby="not-found-title">
      <h1 id="not-found-title" className="itg-page-title not-found-title">
        Page not found
      </h1>
      <p className="itg-page-meta not-found-code">Error 404</p>
      <p className="itg-empty-state-text not-found-message">
        The page you're looking for doesn't exist or has been moved.
      </p>
      <div className="itg-empty-state-actions">
        <Link to="/" className="itg-btn itg-btn-primary">
          Go to the home page
        </Link>
        <Link to="/projects" className="itg-link">
          Browse projects
        </Link>
      </div>
    </section>
  );
}
