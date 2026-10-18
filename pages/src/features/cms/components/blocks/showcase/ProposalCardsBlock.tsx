import {SafeHtml} from '@/components/SafeHtml/SafeHtml';
import {CMS_PAGE_TITLE_CLASS} from '../headings';

export interface ProposalCard {
  type: string;
  title: string;
  organization: string;
  background: string;
  problem: string;
  objectives: string;
}

export interface ProposalCardsData {
  heading?: string;
  footer_html?: string;
  proposals: ProposalCard[];
}

const PROPOSAL_SECTIONS = [
  {key: 'background', label: 'Background'},
  {key: 'problem', label: 'Problem'},
  {key: 'objectives', label: 'Objectives'},
] as const;

export const ProposalCardsBlock = ({ data }: { data: ProposalCardsData }) => {
  const proposals = Array.isArray(data.proposals) ? data.proposals : [];

  return (
    <div className="cms-proposal-cards">
      {data.heading && <h1 className={CMS_PAGE_TITLE_CLASS}>{data.heading}</h1>}
      {proposals.length > 0 && (
        <div className="cms-proposal-list">
          {proposals.map((proposal, i) => {
            const eyebrow = [proposal.type, proposal.organization].filter(Boolean).join(' · ');
            return (
              // Each proposal is a native disclosure; the first one starts open.
              <details key={`${proposal.title}-${i}`} className="cms-proposal proposal-card" open={i === 0}>
                <summary className="cms-proposal-summary">
                  {eyebrow && <span className="itg-eyebrow cms-proposal-eyebrow">{eyebrow}</span>}
                  <h2 className="cms-proposal-title">{proposal.title}</h2>
                  <span className="cms-proposal-toggle" aria-hidden="true">
                    <span className="cms-proposal-toggle-closed">Read ▾</span>
                    <span className="cms-proposal-toggle-open">Hide ▴</span>
                  </span>
                </summary>
                <div className="cms-proposal-body proposal-card-body">
                  {PROPOSAL_SECTIONS.map(({key, label}) =>
                    proposal[key] ? (
                      <section key={key} className="cms-proposal-section">
                        <h3 className="proposal-section-title">{label}</h3>
                        <p className="proposal-text">{proposal[key]}</p>
                      </section>
                    ) : null,
                  )}
                </div>
              </details>
            );
          })}
        </div>
      )}
      {data.footer_html ? (
        <SafeHtml className="itg-panel cms-prose cms-proposal-footer proposal-footer" html={data.footer_html} />
      ) : null}
    </div>
  );
};
