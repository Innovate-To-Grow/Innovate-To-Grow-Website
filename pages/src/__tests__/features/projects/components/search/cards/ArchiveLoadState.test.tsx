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

/** A first load that failed; Try again starts loading again, as the page's rows hook does. */
const RetryHarness = () => {
  const [state, setState] = useState({loading: false, failed: true});
  return <ArchiveLoadState {...state} onRetry={() => setState({loading: true, failed: false})} headingId="heading" />;
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

  it("names All Projects' list while it loads", () => {
    render(inAllProjects(<ArchiveLoadState loading failed={false} headingId="heading" />));

    expect(screen.getByRole('status')).toHaveTextContent('Loading projects…');
  });

  it("names All Projects' list when its first load failed, and while Try again loads it", () => {
    render(inAllProjects(<RetryHarness />));
    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('The project list could not be loaded. Check your connection and try again.');

    fireEvent.click(within(alert).getByRole('button', {name: 'Try again'}));

    expect(screen.getByRole('alert')).toHaveTextContent('Loading projects…');
  });
});
