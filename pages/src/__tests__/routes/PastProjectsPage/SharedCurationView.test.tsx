import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {useState} from 'react';
import {MemoryRouter} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {PastProjectShare} from '@/features/projects/api';
import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {SharedCurationView} from '@/routes/PastProjectsPage/SharedCurationView';

type ViewProps = Parameters<typeof SharedCurationView>[0];

const SHARE: PastProjectShare = {
  id: 'share-1',
  name: 'Water projects',
  rows: [],
  note: '',
  details_text: '',
  version: 1,
  share_url: '/past-projects/share-1',
  can_edit: false,
  created_at: '2026-05-01T00:00:00Z',
};

const view = (status: Partial<ViewProps['status']>, share: PastProjectShare | null = null) => (
  <MemoryRouter>
    <SharedCurationView
      status={{loading: false, error: null, notFound: false, retry: vi.fn(), ...status}}
      conflictMessage={null}
      justSaved={false}
      share={share}
      items={[]}
      onUpdateShare={vi.fn()}
      projects={{rows: [], loading: false, error: null, refetch: vi.fn()}}
      onAddRows={vi.fn()}
    />
  </MemoryRouter>
);

const renderView = (status: Partial<ViewProps['status']>) => render(view(status));

/** A curation whose load failed; Try again loads it again, as usePastProjectShareData does. */
const RetryHarness = () => {
  const [state, setState] = useState<{loading: boolean; error: string | null; share: PastProjectShare | null}>({
    loading: false,
    error: 'Network Error',
    share: null,
  });
  return (
    <>
      {view(
        {loading: state.loading, error: state.error, retry: () => setState({loading: true, error: null, share: null})},
        state.share,
      )}
      <button type="button" onClick={() => setState({loading: false, error: 'Network Error', share: null})}>
        Fail the load
      </button>
      <button type="button" onClick={() => setState({loading: false, error: null, share: SHARE})}>
        Finish the load
      </button>
    </>
  );
};

describe('SharedCurationView', () => {
  afterEach(() => {
    cleanup();
  });

  it('announces that the curation is loading from a status line kept in the page', () => {
    const {rerender} = renderView({loading: true});
    const line = screen.getByRole('status');
    expect(line).toHaveTextContent('Loading curation...');

    rerender(view({}, SHARE));
    expect(line).toBeInTheDocument();
    expect(line).toBeEmptyDOMElement();
  });

  it('keeps Try again, and its focus, while the retry loads, then hands focus to the curation title', () => {
    render(<RetryHarness />);
    const tryAgain = screen.getByRole('button', {name: 'Try again'});
    tryAgain.focus();

    fireEvent.click(tryAgain);
    expect(tryAgain).toBeInTheDocument();
    expect(tryAgain).toHaveFocus();
    expect(tryAgain).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getAllByText('Loading curation...')).toHaveLength(1);

    // A retry that fails again says so in a live region, and Try again works again.
    fireEvent.click(screen.getByRole('button', {name: 'Fail the load'}));
    expect(screen.getByText(/Something went wrong while loading this curation/)).toHaveAttribute('role', 'status');
    expect(tryAgain).toHaveFocus();
    expect(tryAgain).not.toHaveAttribute('aria-disabled');

    fireEvent.click(tryAgain);
    fireEvent.click(screen.getByRole('button', {name: 'Finish the load'}));
    expect(tryAgain).not.toBeInTheDocument();
    expect(screen.getByRole('heading', {level: 1, name: 'Water projects'})).toHaveFocus();
  });

  it('names the builder that saved the curation in its saved notice', () => {
    render(
      <MemoryRouter>
        <SharedCurationView
          status={{loading: false, error: null, notFound: false, retry: vi.fn()}}
          conflictMessage={null}
          justSaved
          builtOn={ALL_PROJECTS_CATALOG}
          share={{...SHARE, can_edit: true}}
          items={[]}
          onUpdateShare={vi.fn()}
          projects={{rows: [], loading: true, error: null, refetch: vi.fn()}}
          onAddRows={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/^Curation saved\./)).toHaveTextContent(
      'Curation saved. It is listed under My Curations on the All Projects page, and you can keep editing it here.',
    );
    expect(screen.getByRole('link', {name: 'All Projects'})).toHaveAttribute('href', '/all-projects');
  });

  it("words the owner's search for more projects as All Projects, which it searches", () => {
    render(
      <MemoryRouter>
        <SharedCurationView
          status={{loading: false, error: null, notFound: false, retry: vi.fn()}}
          conflictMessage={null}
          justSaved={false}
          share={{...SHARE, can_edit: true}}
          items={[]}
          onUpdateShare={vi.fn()}
          projects={{rows: [], loading: true, error: null, refetch: vi.fn()}}
          onAddRows={vi.fn()}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', {level: 2, name: 'Add More Projects'})).toBeInTheDocument();
    expect(screen.getByText('Loading projects...')).toHaveAttribute('role', 'status');
    expect(screen.queryByText('Loading past projects...')).toBeNull();
    // The way back to a builder still names Past Projects.
    expect(screen.getByRole('link', {name: 'Search all past projects'})).toHaveAttribute('href', '/past-projects');
  });

  it('names the tab after a curation that does not exist', () => {
    document.title = 'Past Projects | Innovate to Grow';
    renderView({error: 'Not found', notFound: true});

    expect(screen.getByRole('heading', {level: 1})).toHaveTextContent("This curation isn't available");
    expect(document.title).toBe('Curation not available | Innovate to Grow');
  });

  it('names the tab after a curation that could not be loaded', () => {
    document.title = 'Past Projects | Innovate to Grow';
    renderView({error: 'Network Error'});

    expect(screen.getByRole('heading', {level: 1})).toHaveTextContent("We couldn't load this curation");
    expect(document.title).toBe('Curation could not be loaded | Innovate to Grow');
  });
});
