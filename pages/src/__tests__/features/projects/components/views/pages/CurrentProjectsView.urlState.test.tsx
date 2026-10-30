import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {Link, MemoryRouter, RouterProvider, createMemoryRouter, useLocation} from 'react-router';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {CurrentProjectsView} from '@/features/projects/components/views/pages/CurrentProjectsView';
import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

// 15 CAP and 15 CSE teams, alternating between two industries.
const ROWS: ProjectGridRow[] = Array.from({length: 30}, (_, index) => ({
  id: `0000000${index}`.slice(-8) + '-0000-4000-8000-000000000000',
  semester_label: '2026 Fall',
  class_code: index < 15 ? 'CAP' : 'CSE',
  team_number: String(101 + (index % 15)),
  team_name: `Team ${index + 1}`,
  project_title: `Project ${index + 1}`,
  organization: `Org ${index + 1}`,
  industry: index % 2 ? 'Energy' : 'Agriculture',
  abstract: '',
  student_names: '',
  is_presenting: 'Yes',
}));

const view = (overrides: Partial<Parameters<typeof CurrentProjectsView>[0]> = {}) => (
  <CurrentProjectsView
    title="Current Projects"
    lede="Lede."
    rows={ROWS}
    loading={false}
    error={null}
    classLabels={{CAP: 'Engineering Capstone'}}
    namespace="current-projects"
    emptyMessage="No current projects are available yet."
    {...overrides}
  />
);

const renderRouted = (initialEntries: string[], initialIndex?: number) => {
  const router = createMemoryRouter(
    [
      {path: '/current-projects', element: view()},
      {path: '/projects/:id', element: <h1>Project page</h1>},
      {path: '/news', element: <Link to="/current-projects">Projects</Link>},
    ],
    {initialEntries, initialIndex},
  );
  render(<RouterProvider router={router} />);
  return router;
};

const countLine = () => document.querySelector('.project-grid-count') as HTMLElement;
const table = () => within(document.querySelector('.project-grid-table-wrap') as HTMLElement);

describe('CurrentProjectsView URL state', () => {
  let scrollTo: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    scrollTo = vi.fn();
    vi.stubGlobal('scrollTo', scrollTo);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    Object.defineProperty(window, 'scrollY', {value: 0, configurable: true, writable: true});
  });

  it('starts from the search, filters, sort, page and page size in the URL', () => {
    renderRouted(['/current-projects?class=CAP&industry=Energy&sort=project_title&dir=desc&page=2&per=5']);

    expect(screen.getByLabelText('Class')).toHaveValue('CAP');
    expect(screen.getByLabelText('Industry')).toHaveValue('Energy');
    expect(screen.getByLabelText('Sort by')).toHaveValue('project_title:desc');
    expect(screen.getByLabelText('Per page')).toHaveValue('5');
    expect(countLine()).toHaveTextContent('7 of 30 projects in Engineering Capstone (CAP) and Energy · showing 6–7');
    expect(screen.getByRole('button', {name: 'Page 2'})).toHaveAttribute('aria-current', 'page');
  });

  it('ignores values in the URL it does not understand', () => {
    renderRouted(['/current-projects?class=NOPE&sort=abstract&dir=up&page=-3&per=7']);

    expect(screen.getByLabelText('Class')).toHaveValue('');
    expect(screen.getByLabelText('Sort by')).toHaveValue('class_code:asc');
    expect(screen.getByLabelText('Per page')).toHaveValue('10');
    expect(countLine()).toHaveTextContent('30 projects · showing 1–10');
  });

  it('writes the view into the URL as it changes, replacing the history entry and settling the search first', async () => {
    const router = renderRouted(['/current-projects']);

    fireEvent.change(screen.getByLabelText('Class'), {target: {value: 'CAP'}});
    await waitFor(() => expect(router.state.location.search).toBe('?class=CAP'));
    expect(router.state.historyAction).toBe('REPLACE');

    fireEvent.click(screen.getByRole('button', {name: 'Next'}));
    fireEvent.change(screen.getByLabelText('Sort by'), {target: {value: 'organization:desc'}});
    await waitFor(() => expect(router.state.location.search).toBe('?class=CAP&sort=organization&dir=desc'));

    fireEvent.change(screen.getByLabelText('Per page'), {target: {value: '5'}});
    fireEvent.click(screen.getByRole('button', {name: 'Page 3'}));
    await waitFor(() => expect(router.state.location.search).toBe('?class=CAP&sort=organization&dir=desc&page=3&per=5'));

    fireEvent.change(screen.getByRole('searchbox'), {target: {value: 'Org 1'}});
    // The new search starts on page 1 right away; the text follows once typing settles.
    await waitFor(() => expect(router.state.location.search).toBe('?class=CAP&sort=organization&dir=desc&per=5'));
    await waitFor(() =>
      expect(router.state.location.search).toBe('?value=Org+1&class=CAP&sort=organization&dir=desc&per=5'),
    );
    expect(router.state.historyAction).toBe('REPLACE');
  });

  it('comes back from a project page with Back as the visitor left it, scroll included', async () => {
    const router = renderRouted(['/current-projects']);
    fireEvent.change(screen.getByLabelText('Class'), {target: {value: 'CSE'}});
    fireEvent.click(screen.getByRole('button', {name: 'Next'}));
    await waitFor(() => expect(router.state.location.search).toBe('?class=CSE&page=2'));
    expect(countLine()).toHaveTextContent('15 of 30 projects in CSE · showing 11–15');

    Object.defineProperty(window, 'scrollY', {value: 640, configurable: true, writable: true});
    fireEvent.scroll(window);
    fireEvent.click(table().getAllByRole('link')[0]);
    expect(await screen.findByRole('heading', {name: 'Project page'})).toBeInTheDocument();
    scrollTo.mockClear();

    await act(() => router.navigate(-1));

    expect(screen.getByLabelText('Class')).toHaveValue('CSE');
    expect(countLine()).toHaveTextContent('15 of 30 projects in CSE · showing 11–15');
    expect(scrollTo).toHaveBeenCalledWith(0, 640);
    expect(scrollTo).not.toHaveBeenCalledWith(0, 0);
  });

  it('tells the project page which list, with which view, opened it', async () => {
    const router = renderRouted(['/current-projects?class=CAP']);

    fireEvent.click(table().getAllByRole('link')[0]);
    await screen.findByRole('heading', {name: 'Project page'});

    expect(router.state.location.state).toEqual({from: '/current-projects?class=CAP'});
  });

  it('starts at the top, with a fresh view, when a link opens the list', async () => {
    const router = renderRouted(['/current-projects?class=CAP', '/news'], 1);
    Object.defineProperty(window, 'scrollY', {value: 900, configurable: true, writable: true});

    fireEvent.click(screen.getByRole('link', {name: 'Projects'}));

    expect(await screen.findByLabelText('Class')).toHaveValue('');
    expect(router.state.location.search).toBe('');
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
  });

  it('starts over from the URL when the visitor navigates to the list while it is open', async () => {
    const router = renderRouted(['/current-projects?class=CAP&page=2']);
    expect(screen.getByLabelText('Class')).toHaveValue('CAP');

    await act(() => router.navigate('/current-projects?industry=Energy'));

    expect(screen.getByLabelText('Class')).toHaveValue('');
    expect(screen.getByLabelText('Industry')).toHaveValue('Energy');
    expect(countLine()).toHaveTextContent('15 of 30 projects in Energy · showing 1–10');
  });

  it('keeps the URL while the rows load, then applies it', async () => {
    let location = '';
    const Probe = () => {
      location = useLocation().search;
      return null;
    };
    const tree = (props: Partial<Parameters<typeof CurrentProjectsView>[0]>) => (
      <MemoryRouter initialEntries={['/current-projects?class=CAP&page=2']}>
        {view(props)}
        <Probe />
      </MemoryRouter>
    );
    const {rerender} = render(tree({loading: true, rows: []}));
    expect(location).toBe('?class=CAP&page=2');

    rerender(tree({}));

    expect(screen.getByLabelText('Class')).toHaveValue('CAP');
    expect(countLine()).toHaveTextContent('15 of 30 projects in Engineering Capstone (CAP) · showing 11–15');
    await waitFor(() => expect(location).toBe('?class=CAP&page=2'));
  });
});
