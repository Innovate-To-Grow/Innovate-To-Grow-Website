import type {CMSBlock} from '../../features/cms/api';
import {Link, useLocation} from 'react-router-dom';
import {
  SponsorYearBlock,
  type SponsorYearBlockData,
} from '../../components/CMS/blocks/showcase/SponsorYearBlock';
import {useCMSPage} from '../../components/CMS/useCMSPage';
import './AcknowledgementPage.css';

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
      <h1 className="ack-page-title">Partners &amp; Sponsors</h1>

      <p className="ack-page-lead">
        The Innovate to Grow program thrives thanks to the generous support of our partners and
        sponsors. Their commitment to engineering education and student innovation makes this
        program possible.
      </p>

      <p className="ack-page-text">
        We extend our sincere gratitude to all organizations and individuals who contribute to
        Innovate to Grow through project sponsorship, financial support, mentorship, and judging.
        Your involvement directly impacts the educational experience of UC Merced students and
        helps prepare the next generation of engineers and innovators.
      </p>

      {loading ? (
        <div className="ack-page-loading">Loading sponsors...</div>
      ) : sponsorBlocks.length > 0 ? (
        sponsorBlocks.map((block) => (
          <SponsorYearBlock key={`${block.sort_order}-${block.data.year}`} data={block.data} />
        ))
      ) : (
        <section className="ack-page-section">
          <h2 className="ack-page-section-title">Our Sponsors</h2>
          <div className="ack-page-placeholder">
            <p className="ack-page-text">
              Sponsor logos and acknowledgements will be updated for each event.
            </p>
          </div>
        </section>
      )}

      <section className="ack-page-section">
        <h2 className="ack-page-section-title">Become a Sponsor</h2>
        <p className="ack-page-text">
          Interested in supporting the Innovate to Grow program? Learn more about sponsorship
          opportunities and how your organization can get involved.
        </p>
        <p className="ack-page-text">
          <Link to="/sponsorship" className="ack-page-link">
            View Sponsorship Information
          </Link>
        </p>
        <p className="ack-page-text">
          For questions about sponsorship, please contact us at{' '}
          <a href="mailto:i2g@ucmerced.edu">i2g@ucmerced.edu</a>.
        </p>
      </section>
    </div>
  );
};
