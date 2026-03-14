import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

import { NotFoundPage } from '../../pages/NotFoundPage';
import { BlockRenderer } from './BlockRenderer';
import { useCMSPage } from './useCMSPage';

// CMS block styling
import './CMS.css';

// Per-page wrapper CSS (provides max-width, padding, responsive for page_css_class)
import './page-styles/AboutPage.css';
import './page-styles/FaqPage.css';
import './page-styles/ContactUsPage.css';
import './page-styles/student-page.css';
import './page-styles/capstone-page.css';
import './page-styles/PartnershipPage.css';
import './page-styles/PastEventsPage.css';
import './page-styles/SponsorshipPage.css';
import './page-styles/JudgingPage.css';
import './page-styles/PrivacyPolicyPage.css';
import './page-styles/SampleProposalsPage.css';
import './page-styles/ProjectsHubPage.css';
import './page-styles/EngSLPage.css';
import './page-styles/JudgesPage.css';
import './page-styles/AttendeesPage.css';
import './page-styles/ProjectSubmissionPage.css';
import './page-styles/SponsorAcknowledgementPage.css';

export const CMSPageComponent: React.FC = () => {
  const location = useLocation();
  const route = location.pathname;
  const preview = new URLSearchParams(location.search).has('cms_preview');

  const { page, loading, error } = useCMSPage(route, preview);

  useEffect(() => {
    if (page?.title) {
      document.title = `${page.title} | Innovate to Grow`;
    }
  }, [page?.title]);

  if (loading) {
    return <div className="cms-page-loading" />;
  }

  if (error === 'not_found' || !page) {
    return <NotFoundPage />;
  }

  if (error) {
    return (
      <div className="cms-page-error">
        <p>Something went wrong loading this page.</p>
      </div>
    );
  }

  return (
    <div className={page.page_css_class || 'cms-page'}>
      <BlockRenderer blocks={page.blocks} />
    </div>
  );
};
