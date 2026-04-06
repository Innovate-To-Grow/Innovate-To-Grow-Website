import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach, describe, expect, it, vi} from 'vitest';

import {AcknowledgementPage} from './AcknowledgementPage';

const mockUseCMSPage = vi.fn();

vi.mock('../../components/CMS/useCMSPage', () => ({
  useCMSPage: (...args: unknown[]) => mockUseCMSPage(...args),
}));

describe('AcknowledgementPage', () => {
  beforeEach(() => {
    mockUseCMSPage.mockReset();
    mockUseCMSPage.mockReturnValue({
      page: null,
      loading: false,
      error: null,
      isLivePreview: false,
    });
  });

  it('renders sponsor years from CMS page data', () => {
    mockUseCMSPage.mockReturnValue({
      page: {
        slug: 'acknowledgement',
        route: '/acknowledgement',
        title: 'Partners & Sponsors',
        page_css_class: 'ack-page',
        meta_description: '',
        blocks: [
          {
            block_type: 'sponsor_year',
            sort_order: 0,
            data: {
              year: '2025',
              sponsors: [
                {
                  name: 'Acme Labs',
                  logo_url: 'https://example.com/acme.svg',
                  website: 'https://acme.example.com',
                },
              ],
            },
          },
        ],
      },
      loading: false,
      error: null,
      isLivePreview: false,
    });

    render(
      <MemoryRouter>
        <AcknowledgementPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Partners & Sponsors'})).toBeInTheDocument();
    expect(screen.getByRole('heading', {name: '2025 Sponsors'})).toBeInTheDocument();
    expect(screen.getByText('Acme Labs')).toBeInTheDocument();
    expect(screen.getByAltText('Acme Labs')).toHaveAttribute('src', 'https://example.com/acme.svg');
  });

  it('shows placeholder copy when CMS has no sponsor blocks', () => {
    mockUseCMSPage.mockReturnValue({
      page: {
        slug: 'acknowledgement',
        route: '/acknowledgement',
        title: 'Partners & Sponsors',
        page_css_class: 'ack-page',
        meta_description: '',
        blocks: [
          {
            block_type: 'rich_text',
            sort_order: 0,
            data: {body_html: '<p>Ignored</p>'},
          },
        ],
      },
      loading: false,
      error: null,
      isLivePreview: false,
    });

    render(
      <MemoryRouter>
        <AcknowledgementPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {name: 'Our Sponsors'})).toBeInTheDocument();
    expect(
      screen.getByText('Sponsor logos and acknowledgements will be updated for each event.'),
    ).toBeInTheDocument();
  });

  it('shows placeholder initials when a sponsor has no logo', () => {
    mockUseCMSPage.mockReturnValue({
      page: {
        slug: 'acknowledgement',
        route: '/acknowledgement',
        title: 'Partners & Sponsors',
        page_css_class: 'ack-page',
        meta_description: '',
        blocks: [
          {
            block_type: 'sponsor_year',
            sort_order: 0,
            data: {
              year: '2024',
              sponsors: [
                {
                  name: 'Beta Works',
                  website: '',
                },
              ],
            },
          },
        ],
      },
      loading: false,
      error: null,
      isLivePreview: false,
    });

    const {container} = render(
      <MemoryRouter>
        <AcknowledgementPage />
      </MemoryRouter>,
    );

    expect(screen.queryByAltText('Beta Works')).not.toBeInTheDocument();
    expect(screen.getByText('Beta Works')).toBeInTheDocument();
    expect(container.querySelector('.cms-sponsor-card-placeholder')?.textContent).toBe('B');
  });
});
