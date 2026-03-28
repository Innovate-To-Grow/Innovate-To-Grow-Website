import { useEffect, useMemo, useState } from 'react';
import { useLocation } from 'react-router-dom';

import { NotFoundPage } from '../../pages/NotFoundPage';
import { BlockRenderer } from './BlockRenderer';
import { useCMSPage } from './useCMSPage';

function formatExpiryTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

// CMS block styling
import './CMS.css';

// Per-page wrapper CSS (provides max-width, padding, responsive for page_css_class)
import './page-styles/core/AboutPage.css';
import './page-styles/core/ContactUsPage.css';
import './page-styles/core/FaqPage.css';
import './page-styles/core/HomePage.css';
import './page-styles/core/PrivacyPolicyPage.css';
import './page-styles/core/ProjectsHubPage.css';
import './page-styles/event/AttendeesPage.css';
import './page-styles/event/EventPage.css';
import './page-styles/event/JudgesPage.css';
import './page-styles/event/JudgingPage.css';
import './page-styles/event/PastEventsPage.css';
import './page-styles/event/PostEventHomePage.css';
import './page-styles/event/TemplateEmailPage.css';
import './page-styles/event/VideoPreparationPage.css';
import './page-styles/partnerships/PartnershipPage.css';
import './page-styles/partnerships/ProjectSubmissionPage.css';
import './page-styles/partnerships/SampleProposalsPage.css';
import './page-styles/partnerships/SponsorAcknowledgementPage.css';
import './page-styles/partnerships/SponsorshipPage.css';
import './page-styles/programs/EngSLPage.css';
import './page-styles/programs/EngineeringCapstonePage.css';
import './page-styles/programs/SoftwareCapstonePage.css';
import './page-styles/programs/capstone-page.css';
import './page-styles/students/EventPreparationPage.css';
import './page-styles/students/FerpaAgreementPage.css';
import './page-styles/students/PurchasingReimbursementPage.css';
import './page-styles/students/StudentAgreementPage.css';
import './page-styles/students/StudentsPage.css';
import './page-styles/students/student-page.css';

interface CMSPageComponentProps {
  routeOverride?: string;
}

export const CMSPageComponent: React.FC<CMSPageComponentProps> = ({routeOverride}) => {
  const location = useLocation();
  const route = routeOverride || location.pathname;
  const preview = new URLSearchParams(location.search).has('cms_preview');

  const { page, loading, error, isLivePreview } = useCMSPage(route, preview);
  const [showPreviewModal, setShowPreviewModal] = useState(isLivePreview);

  const expiresAt = page?.expires_at;
  const expiryDisplay = useMemo(() => {
    if (!expiresAt) return null;
    return formatExpiryTime(expiresAt);
  }, [expiresAt]);

  useEffect(() => {
    if (page?.title) {
      const suffix = isLivePreview ? ' [Live Preview]' : '';
      document.title = `${page.title}${suffix} | Innovate to Grow`;
    }
  }, [page?.title, isLivePreview]);

  if (loading) {
    return <div className="cms-page-loading" />;
  }

  if (!isLivePreview && (error === 'not_found' || !page)) {
    return <NotFoundPage />;
  }

  if (!isLivePreview && error) {
    return (
      <div className="cms-page-error">
        <p>Something went wrong loading this page.</p>
      </div>
    );
  }

  return (
    <>
      {isLivePreview && showPreviewModal && (
        <div className="cms-live-preview-overlay" onClick={() => setShowPreviewModal(false)}>
          <div className="cms-live-preview-modal" onClick={(e) => e.stopPropagation()}>
            <span className="cms-live-preview-modal-dot" />
            <p className="cms-live-preview-modal-text">
              Previewing This Page With Content Management System with Admin Permission
            </p>
            {expiryDisplay && (
              <p className="cms-live-preview-modal-expiry">Expires at {expiryDisplay}</p>
            )}
            <button className="cms-live-preview-modal-close" onClick={() => setShowPreviewModal(false)}>
              OK
            </button>
          </div>
        </div>
      )}
      {isLivePreview && !showPreviewModal && (
        <div className="cms-live-preview-badge" onClick={() => setShowPreviewModal(true)}>
          <span className="cms-live-preview-modal-dot" />
          <span>CMS Preview</span>
          {expiryDisplay && (
            <span className="cms-live-preview-badge-expiry">Expires {expiryDisplay}</span>
          )}
        </div>
      )}
      <div className={page?.page_css_class || 'cms-page'}>
        {page && <BlockRenderer blocks={page.blocks} />}
      </div>
    </>
  );
};
