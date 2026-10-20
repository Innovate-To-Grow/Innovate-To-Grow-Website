import type {CMSBlock} from '@/features/cms/api';
import {Link, useLocation} from 'react-router';
import {
  SponsorYearBlock,
  type SponsorYearBlockData,
} from '@/features/cms/components/blocks/showcase/SponsorYearBlock';
import {useCMSPage} from '@/features/cms/components/useCMSPage';

function isSponsorYearBlock(
  block: CMSBlock,
): block is CMSBlock & {block_type: 'sponsor_year'; data: SponsorYearBlockData} {
  if (block.block_type !== 'sponsor_year' || !block.data || typeof block.data !== 'object') {
    return false;
  }

  const data = block.data as Partial<SponsorYearBlockData>;
  return typeof data.year === 'string' && Array.isArray(data.sponsors);
}

export const AcknowledgementPage = () => {
  const location = useLocation();
  const preview = new URLSearchParams(location.search).has('cms_preview');
  const {page, loading} = useCMSPage('/acknowledgement', preview);

  const sponsorBlocks = (page?.blocks ?? []).filter(isSponsorYearBlock);

  return (
    <div className="ack-page">
      <h1 className="itg-page-title ack-page-title">Partners &amp; Sponsors</h1>

      <p className="itg-lead ack-page-lead">
        The Innovate to Grow program thrives thanks to the generous support of our partners and
        sponsors. Their commitment to engineering education and student innovation makes this
        program possible.
      </p>

      <div className="itg-content ack-page-content">
        <p>
          We extend our sincere gratitude to all organizations and individuals who contribute to
          Innovate to Grow through project sponsorship, financial support, mentorship, and judging.
          Your involvement directly impacts the educational experience of UC Merced students and
          helps prepare the next generation of engineers and innovators.
        </p>
      </div>

      {/* Sponsors come from the CMS page's sponsor-year blocks; with none there is nothing to list. */}
      {loading ? (
        <p className="ack-page-loading" role="status">Loading sponsors...</p>
      ) : (
        sponsorBlocks.map((block) => (
          <SponsorYearBlock key={`${block.sort_order}-${block.data.year}`} data={block.data} />
        ))
      )}

      <section className="itg-panel ack-page-section ack-page-cta" aria-labelledby="ack-become-sponsor">
        <h2 id="ack-become-sponsor" className="itg-section-title ack-page-section-title">Become a Sponsor</h2>
        <div className="itg-content ack-page-content">
          <p>
            Interested in supporting the Innovate to Grow program? Learn more about sponsorship
            opportunities and how your organization can get involved.
          </p>
        </div>
        <p className="ack-page-actions">
          <Link to="/sponsorship" className="itg-btn itg-btn-primary itg-btn-lg ack-page-link">
            View Sponsorship Information
          </Link>
        </p>
        <div className="itg-content ack-page-content">
          <p>
            For questions about sponsorship, please contact us at{' '}
            <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
          </p>
        </div>
      </section>
    </div>
  );
};
