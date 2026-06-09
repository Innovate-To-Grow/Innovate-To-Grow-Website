import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {describe, expect, it} from 'vitest';

import {ContactInfoBlock} from '@/features/cms/components/blocks/content/ContactInfoBlock';
import {FaqListBlock} from '@/features/cms/components/blocks/content/FaqListBlock';
import {ImageTextBlock} from '@/features/cms/components/blocks/content/ImageTextBlock';
import {LinkListBlock} from '@/features/cms/components/blocks/content/LinkListBlock';
import {RichTextBlock} from '@/features/cms/components/blocks/content/RichTextBlock';
import {NavigationGridBlock} from '@/features/cms/components/blocks/navigation/NavigationGridBlock';
import {SectionGroupBlock} from '@/features/cms/components/blocks/navigation/SectionGroupBlock';
import {ProposalCardsBlock} from '@/features/cms/components/blocks/showcase/ProposalCardsBlock';
import {SponsorYearBlock} from '@/features/cms/components/blocks/showcase/SponsorYearBlock';

describe('miscellaneous CMS blocks', () => {
  it('renders contact values with protocol-specific links', () => {
    render(
      <ContactInfoBlock
        data={{
          heading: 'Contact',
          items: [
            {label: 'Email', value: 'i2g@example.com', type: 'email'},
            {label: 'Phone', value: '+15551234567', type: 'phone'},
            {label: 'Website', value: 'https://example.com', type: 'url'},
            {label: 'Office', value: 'Kolligian Library', type: 'text'},
          ],
        }}
      />,
    );

    expect(screen.getByRole('heading', {name: 'Contact'})).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'i2g@example.com'})).toHaveAttribute('href', 'mailto:i2g@example.com');
    expect(screen.getByRole('link', {name: '+15551234567'})).toHaveAttribute('href', 'tel:+15551234567');
    expect(screen.getByRole('link', {name: 'https://example.com'})).toHaveAttribute('target', '_blank');
    expect(screen.getByText('Kolligian Library')).toBeInTheDocument();
  });

  it('renders rich content, FAQs, and image-text content', () => {
    render(
      <>
        <RichTextBlock data={{heading: 'Overview', heading_level: 3, body_html: '<p>Program intro</p>'}} />
        <FaqListBlock data={{heading: 'FAQ', items: [{question: 'Who can apply?', answer_html: '<p>Teams</p>'}]}} />
        <ImageTextBlock
          data={{
            heading: 'Capstone',
            image_url: '/hero.png',
            image_alt: 'Students presenting',
            body_html: '<p>Project body</p>',
          }}
        />
      </>,
    );

    expect(screen.getByRole('heading', {level: 3, name: 'Overview'})).toBeInTheDocument();
    expect(screen.getByText('Program intro')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: 'Who can apply?'})).toBeInTheDocument();
    expect(screen.getByText('Teams')).toBeInTheDocument();
    expect(screen.getByRole('img', {name: 'Students presenting'})).toHaveAttribute('loading', 'lazy');
    expect(screen.getByText('Project body')).toBeInTheDocument();
  });

  it('renders internal and external link-list and navigation-grid items', () => {
    render(
      <MemoryRouter>
        <LinkListBlock
          data={{
            heading: 'Resources',
            items: [
              {label: 'Projects', url: '/projects', description: 'Browse'},
              {label: 'External', url: 'https://example.com', is_external: true},
            ],
          }}
        />
        <NavigationGridBlock
          data={{
            heading: 'Navigate',
            items: [
              {title: 'Schedule', url: '/schedule', description: 'Agenda'},
              {title: 'Partner', url: 'https://partner.example', is_external: true},
            ],
          }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole('link', {name: 'Projects'})).toHaveAttribute('href', '/projects');
    expect(screen.getByText(/Browse/)).toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'External'})).toHaveAttribute('target', '_blank');
    expect(screen.getByRole('link', {name: 'Schedule'})).toHaveAttribute('href', '/schedule');
    expect(screen.getByRole('link', {name: 'Partner'})).toHaveAttribute('target', '_blank');
  });

  it('renders grouped sections and proposal cards', () => {
    render(
      <>
        <SectionGroupBlock
          data={{
            heading: 'Group',
            sections: [{heading: 'Section A', heading_level: 4, body_html: '<p>Section copy</p>'}],
          }}
        />
        <ProposalCardsBlock
          data={{
            heading: 'Sample Proposals',
            footer_html: '<p>Footer note</p>',
            proposals: [
              {
                type: 'Engineering',
                title: 'Smart Sensor',
                organization: 'Acme',
                background: 'Background copy',
                problem: 'Problem copy',
                objectives: 'Objectives copy',
              },
            ],
          }}
        />
      </>,
    );

    expect(screen.getByRole('heading', {name: 'Group'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 4, name: 'Section A'})).toBeInTheDocument();
    expect(screen.getByText('Section copy')).toBeInTheDocument();
    expect(screen.getByText(/SAMPLE Project Proposal - Engineering/)).toBeInTheDocument();
    expect(screen.getByText('Smart Sensor')).toBeInTheDocument();
    expect(screen.getByText('Footer note')).toBeInTheDocument();
  });

  it('normalizes sponsor year data and hides invalid sponsor groups', () => {
    const {container, unmount} = render(
      <SponsorYearBlock
        data={{
          year: ' 2026 ',
          sponsors: [
            {name: ' Acme ', logo_url: '/logo.png', website: 'https://acme.example'},
            {name: 'No Logo'},
            {name: ''},
          ],
        }}
      />,
    );

    expect(screen.getByRole('heading', {name: '2026 Sponsors'})).toBeInTheDocument();
    expect(screen.getByRole('link', {name: /Acme/})).toHaveAttribute('href', 'https://acme.example');
    expect(screen.getByRole('img', {name: 'Acme'})).toHaveAttribute('src', '/logo.png');
    expect(screen.getByText('No Logo')).toBeInTheDocument();

    unmount();
    const empty = render(<SponsorYearBlock data={{year: '', sponsors: []}} />);
    expect(empty.container).toBeEmptyDOMElement();
    expect(container).toBeDefined();
  });
});
