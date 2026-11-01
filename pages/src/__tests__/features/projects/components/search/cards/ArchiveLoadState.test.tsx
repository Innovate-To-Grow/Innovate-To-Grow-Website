import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {useState, type ReactElement} from 'react';
import {afterEach, describe, expect, it} from 'vitest';

import {ALL_PROJECTS_CATALOG} from '@/features/projects/catalog/catalogs';
import {ProjectCatalogContext} from '@/features/projects/catalog/projectCatalog';
import {ArchiveLoadState} from '@/features/projects/components/search/cards/ArchiveLoadState';

// The loading line and first-load failure name the list the page searches: the archive on Past Projects (the
// default), every project on All Projects.

const inAllProjects = (ui: ReactElement) => (
  <ProjectCatalogContext.Provider value={ALL_PROJECTS_CATALOG}>{ui}</ProjectCatalogContext.Provider>
);

/** A first load that failed; Try Again starts loading again, as the page's rows hook does. */
const RetryHarness = ({loadingClassName}: {loadingClassName?: string}) => {
  const [state, setState] = useState({loading: false, failed: true});
  return (
    <ArchiveLoadState
      {...state}
      onRetry={() => setState({loading: true, failed: false})}
      headingId="heading"
      loadingClassName={loadingClassName}
    />
  );
};

describe('ArchiveLoadState', () => {
  afterEach(cleanup);

  it('names the past-project archive without a catalog', () => {
    const {rerender} = render(<ArchiveLoadState loading failed={false} headingId="heading" />);
    expect(screen.getByRole('status')).toHaveTextContent('Loading past projects…');

    rerender(<ArchiveLoadState loading={false} failed headingId="heading" />);
    expect(screen.getByRole('alert')).toHaveTextContent(
      'The past-project archive could not be loaded. Check your connection and try again.',
    );
  });

  it('shows the site loading indicator inside its status line, holding the room it was given', () => {
    render(<ArchiveLoadState loading failed={false} headingId="heading" loadingClassName="room" />);

    const status = screen.getByRole('status');
    expect(status).toHaveClass('past-projects-loading-line', 'room');
    expect(status.querySelector('.loading-indicator .loading-indicator-spinner')).toHaveAttribute('aria-hidden', 'true');
    expect(within(status).getByText('Loading past projects…')).toHaveClass('loading-indicator-label');
  });

  it('keeps the room through a failure, with an outline Try Again, and loads again behind the indicator', () => {
    render(<RetryHarness loadingClassName="room" />);
    const alert = screen.getByRole('alert');
    // The failure holds the loading line's room, so the page under it does not move up.
    expect(alert).toHaveClass('past-projects-archive-failed', 'room');
    expect(screen.getByRole('status')).not.toHaveClass('room');
    // Inside a working page: an outline button, not a second primary one.
    const tryAgain = within(alert).getByRole('button', {name: 'Try Again'});
    expect(tryAgain).toHaveClass('itg-btn', 'itg-btn-outline');
    expect(tryAgain).not.toHaveClass('itg-btn-primary');

    fireEvent.click(tryAgain);

    expect(screen.getByRole('alert')).toHaveClass('room');
    expect(screen.getByRole('alert').querySelector('.loading-indicator-spinner')).not.toBeNull();
    expect(within(screen.getByRole('alert')).getByText('Loading past projects…')).toHaveClass('loading-indicator-label');
  });

  it("names All Projects' list while it loads", () => {
    render(inAllProjects(<ArchiveLoadState loading failed={false} headingId="heading" />));

    expect(screen.getByRole('status')).toHaveTextContent('Loading projects…');
  });

  it("names All Projects' list when its first load failed, and while Try Again loads it", () => {
    render(inAllProjects(<RetryHarness />));
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('The project list could not be loaded. Check your connection and try again.');

    fireEvent.click(within(alert).getByRole('button', {name: 'Try Again'}));

    expect(screen.getByRole('alert')).toHaveTextContent('Loading projects…');
  });
});
