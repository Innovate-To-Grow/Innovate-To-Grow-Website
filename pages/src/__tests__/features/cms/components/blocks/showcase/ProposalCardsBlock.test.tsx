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

  it('renders the wrapper and the heading as the page title when provided', () => {
    const {container} = render(
      <ProposalCardsBlock data={{heading: 'Proposals', proposals: []}} />,
    );
    expect(container.querySelector('.cms-proposal-cards')).not.toBeNull();
    expect(screen.getByRole('heading', {name: 'Proposals', level: 1})).toHaveClass(
      'itg-page-title',
      'cms-page-title',
    );
    expect(container.querySelector('.cms-proposal-list')).toBeNull();
  });

  it('omits the heading when not provided', () => {
    render(<ProposalCardsBlock data={{proposals: []}} />);
    expect(screen.queryByRole('heading')).toBeNull();
  });

  it('renders each proposal as a disclosure with an eyebrow, an h2 title and h3 sections', () => {
    const {container} = render(<ProposalCardsBlock data={{proposals: [proposal]}} />);

    const details = container.querySelector('details.cms-proposal');
    expect(details).not.toBeNull();
    const summary = details?.querySelector('summary');
    expect(summary?.querySelector('.itg-eyebrow')?.textContent).toBe('Research · ACME Lab');
    expect(screen.getByRole('heading', {name: 'Solar Tracker', level: 2})).toBeInTheDocument();
    expect(summary?.contains(screen.getByRole('heading', {name: 'Solar Tracker', level: 2}))).toBe(true);

    expect(screen.getByRole('heading', {name: 'Background', level: 3})).toBeInTheDocument();
    expect(screen.getByText('Background text')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Problem', level: 3})).toBeInTheDocument();
    expect(screen.getByText('Problem text')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Objectives', level: 3})).toBeInTheDocument();
    expect(screen.getByText('Objectives text')).toBeInTheDocument();
  });

  it('opens only the first proposal and draws an open/close indicator', () => {
    const {container} = render(
      <ProposalCardsBlock data={{proposals: [proposal, {...proposal, type: 'Design', title: 'Second'}]}} />,
    );
    const details = container.querySelectorAll<HTMLDetailsElement>('details.proposal-card');
    expect(details).toHaveLength(2);
    expect(details[0].open).toBe(true);
    expect(details[1].open).toBe(false);

    const toggle = details[1].querySelector('.cms-proposal-toggle');
    expect(toggle).toHaveAttribute('aria-hidden', 'true');
    expect(toggle?.querySelector('.cms-proposal-toggle-closed')?.textContent).toBe('Read ▾');
    expect(toggle?.querySelector('.cms-proposal-toggle-open')?.textContent).toBe('Hide ▴');
  });

  it('builds the eyebrow from whichever of type and organization are present', () => {
    const {container} = render(
      <ProposalCardsBlock
        data={{
          proposals: [
            {...proposal, organization: ''},
            {...proposal, type: '', title: 'Org only'},
            {...proposal, type: '', organization: '', title: 'Neither'},
          ],
        }}
      />,
    );
    const eyebrows = container.querySelectorAll('.cms-proposal-eyebrow');
    expect(eyebrows).toHaveLength(2);
    expect(eyebrows[0].textContent).toBe('Research');
    expect(eyebrows[1].textContent).toBe('ACME Lab');
  });

  it('skips empty proposal sections', () => {
    render(<ProposalCardsBlock data={{proposals: [{...proposal, problem: ''}]}} />);
    expect(screen.queryByRole('heading', {name: 'Problem'})).toBeNull();
    expect(screen.getByRole('heading', {name: 'Background', level: 3})).toBeInTheDocument();
  });

  it('renders footer_html once, after the list, as a feature panel', () => {
    const {container} = render(
      <ProposalCardsBlock
        data={{proposals: [proposal, {...proposal, title: 'Second'}], footer_html: '<p>Apply by Friday</p>'}}
      />,
    );
    const footers = container.querySelectorAll('.proposal-footer');
    expect(footers).toHaveLength(1);
    expect(footers[0]).toHaveClass('itg-panel', 'cms-prose');
    expect(container.querySelector('.cms-proposal-list')?.contains(footers[0])).toBe(false);
    expect(screen.getByText('Apply by Friday')).toBeInTheDocument();
  });

  it('omits the footer when not provided', () => {
    const {container} = render(<ProposalCardsBlock data={{proposals: [proposal]}} />);
    expect(container.querySelector('.proposal-footer')).toBeNull();
  });
});
