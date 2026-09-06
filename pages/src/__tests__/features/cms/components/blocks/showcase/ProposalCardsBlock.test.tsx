import {cleanup, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {ProposalCardsBlock} from '@/features/cms/components/blocks/showcase/ProposalCardsBlock';

const proposal = {
  type: 'Research',
  title: 'Solar Tracker',
  organization: 'ACME Lab',
  background: 'Background text',
  problem: 'Problem text',
  objectives: 'Objectives text',
};

describe('ProposalCardsBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the wrapper and heading when provided', () => {
    const {container} = render(
      <ProposalCardsBlock data={{heading: 'Proposals', proposals: []}} />,
    );
    expect(container.querySelector('.cms-proposal-cards')).not.toBeNull();
    expect(screen.getByRole('heading', {name: 'Proposals', level: 1})).toBeInTheDocument();
  });

  it('omits the heading when not provided', () => {
    render(<ProposalCardsBlock data={{proposals: []}} />);
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('renders a card per proposal with the fixed fields and sections', () => {
    render(<ProposalCardsBlock data={{proposals: [proposal]}} />);

    expect(screen.getByText('SAMPLE Project Proposal - Research')).toBeInTheDocument();
    expect(screen.getByText('Solar Tracker')).toBeInTheDocument();
    expect(screen.getByText('ACME Lab')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Background', level: 3})).toBeInTheDocument();
    expect(screen.getByText('Background text')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Problem', level: 3})).toBeInTheDocument();
    expect(screen.getByText('Problem text')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Objectives', level: 3})).toBeInTheDocument();
    expect(screen.getByText('Objectives text')).toBeInTheDocument();
  });

  it('renders multiple proposal cards', () => {
    const {container} = render(
      <ProposalCardsBlock data={{proposals: [proposal, {...proposal, type: 'Design'}]}} />,
    );
    expect(container.querySelectorAll('.proposal-card')).toHaveLength(2);
  });

  it('renders footer_html through SafeHtml with the footer class when provided', () => {
    const {container} = render(
      <ProposalCardsBlock
        data={{proposals: [proposal], footer_html: '<p>Apply by Friday</p>'}}
      />,
    );
    const footer = container.querySelector('.proposal-footer');
    expect(footer).not.toBeNull();
    expect(screen.getByText('Apply by Friday')).toBeInTheDocument();
  });

  it('omits the footer when not provided', () => {
    const {container} = render(<ProposalCardsBlock data={{proposals: [proposal]}} />);
    expect(container.querySelector('.proposal-footer')).toBeNull();
  });
});
