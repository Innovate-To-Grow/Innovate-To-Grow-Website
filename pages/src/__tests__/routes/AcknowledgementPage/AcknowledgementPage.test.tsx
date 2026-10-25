import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {AcknowledgementPage} from '@/routes/AcknowledgementPage/AcknowledgementPage';

const mockUseCMSPage = vi.fn();

vi.mock('@/features/cms/components/useCMSPage', () => ({
  useCMSPage: (...args: unknown[]) => mockUseCMSPage(...args),
}));

const cmsPage = {
  slug: 'acknowledgement',
  route: '/acknowledgement',
  title: 'Partners & Sponsors',
  page_css_class: '',
  meta_description: '',
  blocks: [
    {
      block_type: 'rich_text',
      sort_order: 0,
      data: {heading: 'Partners & Sponsors', heading_level: 1, body_html: '<p>Thank you to our sponsors.</p>'},
    },
    {
      block_type: 'sponsor_year',
      sort_order: 10,
      data: {year: '2025', sponsors: [{name: 'Acme Labs', logo_url: 'https://example.com/acme.svg'}]},
    },
  ],
};

describe('AcknowledgementPage', () => {
  beforeEach(() => {
    mockUseCMSPage.mockReset();
    mockUseCMSPage.mockReturnValue({
      page: cmsPage,
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: false,
      retry: vi.fn(),
    });
  });

  it('renders the /acknowledgement CMS page whatever the current path, as in an embed', () => {
    render(
      <MemoryRouter initialEntries={['/_embed/sponsors']}>
        <AcknowledgementPage />
      </MemoryRouter>,
    );

    expect(mockUseCMSPage).toHaveBeenCalledWith('/acknowledgement', false);
    expect(screen.getByRole('heading', {level: 1, name: 'Partners & Sponsors'})).toBeInTheDocument();
    expect(screen.getByText('Thank you to our sponsors.')).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: '2025 Sponsors'})).toBeInTheDocument();
    expect(screen.getByAltText('Acme Labs')).toHaveAttribute('src', 'https://example.com/acme.svg');
  });

  it('has no copy of its own', () => {
    mockUseCMSPage.mockReturnValue({
      page: {...cmsPage, blocks: []},
      redirectTo: null,
      loading: false,
      error: null,
      isLivePreview: false,
      retry: vi.fn(),
    });

    const {container} = render(
      <MemoryRouter>
        <AcknowledgementPage />
      </MemoryRouter>,
    );

    expect(container.textContent).not.toMatch(/i2g@ucmerced\.edu|Become a Sponsor|View Sponsorship Information|generous support/);
  });
});
