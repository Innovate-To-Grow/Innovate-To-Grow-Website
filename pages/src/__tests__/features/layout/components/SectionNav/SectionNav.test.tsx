import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {MemoryRouter, Route, Routes, useLocation} from 'react-router';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {MenuItem} from '@/features/layout/api';
import {SectionNav, SectionSelect} from '@/features/layout/components/SectionNav/SectionNav';

const item = (title: string, url: string, children: MenuItem[] = [], extra: Partial<MenuItem> = {}): MenuItem => ({
  title,
  url,
  type: 'app',
  open_in_new_tab: false,
  children,
  ...extra,
});

const projects = item('Projects', '/projects', [
  item('Current Projects', '/current-projects'),
  item('Past Projects', '/past-projects'),
  item('Project Submission', '/project-submission'),
  item('Sample Proposals', '/sample-proposals'),
  item('Showcase video', 'https://www.youtube.com/@ucmerced', [], {type: 'external', open_in_new_tab: true}),
]);

const LocationProbe = () => <output data-testid="location">{useLocation().pathname}</output>;

const renderAt = (ui: React.ReactNode, path = '/current-projects') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      {ui}
      <Routes>
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  );

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('SectionNav', () => {
  it('renders the section panel with its title link and pages, marking the current page', () => {
    renderAt(<SectionNav section={projects} current={{currentPath: '/current-projects', isExact: true}} />);

    const nav = screen.getByRole('navigation', {name: 'Projects'});
    const title = within(nav).getByRole('heading', {level: 2, name: 'Projects'});
    expect(within(title).getByRole('link', {name: 'Projects'})).toHaveAttribute('href', '/projects');
    expect(within(title).getByRole('link', {name: 'Projects'})).not.toHaveAttribute('aria-current');

    const links = within(within(nav).getByRole('list')).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual([
      'Current Projects',
      'Past Projects',
      'Project Submission',
      'Sample Proposals',
      'Showcase video',
    ]);
    expect(links[0]).toHaveAttribute('aria-current', 'page');
    expect(links[1]).not.toHaveAttribute('aria-current');
  });

  it('marks the list page of a detail route as current (not the page itself)', () => {
    renderAt(<SectionNav section={projects} current={{currentPath: '/past-projects', isExact: false}} />, '/past-projects/abc');
    expect(screen.getByRole('link', {name: 'Past Projects'})).toHaveAttribute('aria-current', 'true');
  });

  it('marks the section title on the section landing page', () => {
    renderAt(<SectionNav section={projects} current={{currentPath: '/projects', isExact: true}} />, '/projects');
    expect(screen.getByRole('link', {name: 'Projects'})).toHaveAttribute('aria-current', 'page');
  });

  it('navigates in-app pages through the router and opens configured external pages in a new tab', () => {
    renderAt(<SectionNav section={projects} current={{currentPath: '/current-projects', isExact: true}} />);

    fireEvent.click(screen.getByRole('link', {name: 'Sample Proposals'}));
    expect(screen.getByTestId('location')).toHaveTextContent('/sample-proposals');

    const external = screen.getByRole('link', {name: 'Showcase video'});
    expect(external).toHaveAttribute('href', 'https://www.youtube.com/@ucmerced');
    expect(external).toHaveAttribute('target', '_blank');
    expect(external).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('renders nested pages as a nested list', () => {
    const section = item('About', '/about', [item('Programs', '/programs', [item('Capstone', '/capstone')])]);
    renderAt(<SectionNav section={section} current={{currentPath: '/capstone', isExact: true}} />, '/capstone');
    const nested = screen.getByRole('link', {name: 'Capstone'}).closest('ul');
    expect(nested).toHaveClass('section-nav-list--nested');
    expect(screen.getByRole('link', {name: 'Capstone'})).toHaveAttribute('aria-current', 'page');
  });
});

describe('SectionSelect', () => {
  it('labels the select "In <Section>" and selects the current page', () => {
    renderAt(<SectionSelect section={projects} current={{currentPath: '/past-projects', isExact: true}} />, '/past-projects');

    const select = screen.getByRole('combobox', {name: 'In Projects'}) as HTMLSelectElement;
    expect(Array.from(select.options).map((option) => option.textContent)).toEqual([
      'Projects',
      'Current Projects',
      'Past Projects',
      'Project Submission',
      'Sample Proposals',
      'Showcase video',
    ]);
    expect(select.selectedOptions[0]).toHaveTextContent('Past Projects');
  });

  it('navigates to the chosen page', () => {
    renderAt(<SectionSelect section={projects} current={{currentPath: '/current-projects', isExact: true}} />);

    const select = screen.getByRole('combobox', {name: 'In Projects'}) as HTMLSelectElement;
    const proposals = Array.from(select.options).find((option) => option.textContent === 'Sample Proposals')!;
    fireEvent.change(select, {target: {value: proposals.value}});

    expect(screen.getByTestId('location')).toHaveTextContent('/sample-proposals');
  });

  it('opens new-tab pages in a new tab', () => {
    const open = vi.spyOn(window, 'open').mockReturnValue(null);
    renderAt(<SectionSelect section={projects} current={{currentPath: '/current-projects', isExact: true}} />);

    const select = screen.getByRole('combobox', {name: 'In Projects'}) as HTMLSelectElement;
    const video = Array.from(select.options).find((option) => option.textContent === 'Showcase video')!;
    fireEvent.change(select, {target: {value: video.value}});

    expect(open).toHaveBeenCalledWith('https://www.youtube.com/@ucmerced', '_blank', 'noopener,noreferrer');
    expect(screen.getByTestId('location')).toHaveTextContent('/current-projects');
  });

  it('shows a placeholder when the page is not one of the options', () => {
    renderAt(<SectionSelect section={projects} current={{currentPath: '/elsewhere', isExact: true}} />, '/elsewhere');
    const select = screen.getByRole('combobox', {name: 'In Projects'}) as HTMLSelectElement;
    expect(select.value).toBe('');
    expect(select.selectedOptions[0]).toHaveTextContent('Choose a page');
  });
});
