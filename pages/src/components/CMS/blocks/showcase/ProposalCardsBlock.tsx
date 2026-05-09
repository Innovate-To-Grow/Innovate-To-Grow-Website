import {SafeHtml} from '../../../SafeHtml/SafeHtml';

interface Proposal {
  type: string;
  title: string;
  organization: string;
  background: string;
  problem: string;
  objectives: string;
}

interface ProposalCardsData {
  heading?: string;
  footer_html?: string;
  proposals: Proposal[];
}

export const ProposalCardsBlock = ({ data }: { data: ProposalCardsData }) => {
  return (
    <div className="cms-proposal-cards">
      {data.heading && <h1>{data.heading}</h1>}
      {data.proposals.map((proposal, i) => (
        <div key={i} className="proposal-card">
          <div className="proposal-card-header">
            SAMPLE Project Proposal - {proposal.type}
          </div>
          <div className="proposal-card-body">
            <div className="proposal-field">
              <span className="proposal-label">Project Title:</span> {proposal.title}
            </div>
            <div className="proposal-field">
              <span className="proposal-label">Organization Name:</span> {proposal.organization}
            </div>
            <div className="proposal-field">
              <span className="proposal-label">Primary Contact First Name:</span> ----------
            </div>
            <div className="proposal-field">
              <span className="proposal-label">Primary Contact Last Name:</span> ----------
            </div>
            <div className="proposal-field">
              <span className="proposal-label">Primary Contact Email:</span> ----------
            </div>
            <div className="proposal-field">
              <span className="proposal-label">Primary Contact Phone:</span> ----------
            </div>

            <h3 className="proposal-section-title">Background</h3>
            <p className="proposal-text">{proposal.background}</p>

            <h3 className="proposal-section-title">Problem</h3>
            <p className="proposal-text">{proposal.problem}</p>

            <h3 className="proposal-section-title">Objectives</h3>
            <p className="proposal-text">{proposal.objectives}</p>

            {data.footer_html ? <SafeHtml className="proposal-footer" html={data.footer_html} /> : null}
          </div>
        </div>
      ))}
    </div>
  );
};
