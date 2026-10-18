import {describe, expect, it} from 'vitest';

import type {MenuItem} from '@/features/layout/api';
import {
  allowsSectionNav,
  ariaCurrentFor,
  menuItemPath,
  normalizePath,
  resolveSection,
  sectionOptions,
} from '@/features/layout/sections';

const item = (title: string, url: string, children: MenuItem[] = [], type: MenuItem['type'] = 'app'): MenuItem => ({
  title,
  url,
  type,
  open_in_new_tab: false,
  children,
});

// Mirrors the production main menu (GET /api/layout/), including its duplicates:
// /project-submission is both a top-level item and a Projects child, /students is
// a top-level section and an Events child, /event is the Events url and its first child.
const MENU: MenuItem[] = [
  item('Home', '/', [], 'home'),
  item('About', '/about', [item('Engineering Capstone', '/engineering-capstone'), item('Software Eng. Capstone', '/software-capstone')]),
  item('Events', '/event', [
    item('Event Info', '/event'),
    item('Registration', '/event-registration'),
    item('Schedule', '/schedule'),
    item('For Judges', '/judges'),
    item('For Students', '/students'),
    item('Past Events', '/past-events'),
  ]),
  item('Projects', '/projects', [
    item('Current Projects', '/current-projects'),
    item('Past Projects', '/past-projects'),
    item('Project Submission', '/project-submission'),
    item('Sample Proposals', '/sample-proposals'),
  ]),
  item('Partner with Us', '/partnership', [item('Newsletter', '/subscribe'), item('Judge', '/judges')]),
  item('Students', '/students', [item('Student Agreement', '/student-agreement')]),
  item('Project Submission', '/project-submission'),
  item('News', '/news'),
];

const titleOf = (index: number | null) => (index === null ? null : MENU[index].title);

describe('normalizePath', () => {
  it('drops query, hash, duplicate and trailing slashes, and case', () => {
    expect(normalizePath('/Past-Projects/?x=1#top')).toBe('/past-projects');
    expect(normalizePath('//news//')).toBe('/news');
    expect(normalizePath('')).toBe('/');
    expect(normalizePath('/')).toBe('/');
  });
});

describe('menuItemPath', () => {
  it('returns same-origin paths only', () => {
    expect(menuItemPath({url: '/event-registration?event=spring'})).toBe('/event-registration');
    expect(menuItemPath({url: `${window.location.origin}/news/`})).toBe('/news');
    expect(menuItemPath({url: 'https://www.ucmerced.edu/about'})).toBeNull();
    expect(menuItemPath({url: '//evil.example/x'})).toBeNull();
    expect(menuItemPath({url: '#anchor'})).toBeNull();
    expect(menuItemPath({url: ''})).toBeNull();
  });
});

describe('resolveSection', () => {
  it('maps a child page to its section for both the menu row and the sidebar', () => {
    const match = resolveSection(MENU, '/current-projects');
    expect(titleOf(match.menuIndex)).toBe('Projects');
    expect(match.section?.title).toBe('Projects');
    expect(match).toMatchObject({currentPath: '/current-projects', isExact: true});
  });

  it('underlines a childless top-level duplicate but keeps the sidebar of the section it belongs to', () => {
    const match = resolveSection(MENU, '/project-submission');
    expect(titleOf(match.menuIndex)).toBe('Project Submission');
    expect(match.section?.title).toBe('Projects');
  });

  it('prefers a section whose own url is the page', () => {
    const students = resolveSection(MENU, '/students');
    expect(titleOf(students.menuIndex)).toBe('Students');
    expect(students.section?.title).toBe('Students');

    const events = resolveSection(MENU, '/event');
    expect(titleOf(events.menuIndex)).toBe('Events');
    expect(events.section?.title).toBe('Events');
  });

  it('uses the first section in menu order when a page is listed twice', () => {
    expect(resolveSection(MENU, '/judges').section?.title).toBe('Events');
  });

  it('maps detail routes onto their list page (not exact)', () => {
    expect(resolveSection(MENU, '/projects/3f2a')).toMatchObject({currentPath: '/current-projects', isExact: false});
    expect(resolveSection(MENU, '/past-projects/project/9')).toMatchObject({currentPath: '/past-projects', isExact: false});
    expect(resolveSection(MENU, '/past-projects/share-123')).toMatchObject({currentPath: '/past-projects', isExact: false});
    expect(resolveSection(MENU, '/past-projects/share-123').section?.title).toBe('Projects');

    const news = resolveSection(MENU, '/news/42');
    expect(titleOf(news.menuIndex)).toBe('News');
    expect(news.section).toBeNull();

    const event = resolveSection(MENU, '/events/spring-2026');
    expect(event.section?.title).toBe('Events');
    expect(event.currentPath).toBe('/past-events');
  });

  it('falls back to the closest ancestor page for nested CMS pages', () => {
    const match = resolveSection(MENU, '/about/history');
    expect(match.section?.title).toBe('About');
    expect(match).toMatchObject({currentPath: '/about', isExact: false});
  });

  it('has no section on the home page or on pages outside the menu', () => {
    const home = resolveSection(MENU, '/');
    expect(titleOf(home.menuIndex)).toBe('Home');
    expect(home.section).toBeNull();

    expect(resolveSection(MENU, '/login')).toMatchObject({menuIndex: null, section: null});
    expect(resolveSection([], '/current-projects')).toMatchObject({menuIndex: null, section: null});
    expect(resolveSection(null, '/news')).toMatchObject({menuIndex: null, section: null});
  });
});

describe('allowsSectionNav', () => {
  it('is off on home, auth/account and isolated routes', () => {
    expect(allowsSectionNav('/')).toBe(false);
    expect(allowsSectionNav('/login')).toBe(false);
    expect(allowsSectionNav('/account/past-project-curation-shared-links')).toBe(false);
    expect(allowsSectionNav('/verify-email')).toBe(false);
    expect(allowsSectionNav('/_embed/schedule')).toBe(false);
    expect(allowsSectionNav('/current-projects', '?_isolated=1')).toBe(false);
  });

  it('is on for content pages', () => {
    expect(allowsSectionNav('/current-projects')).toBe(true);
    expect(allowsSectionNav('/accounting-faq')).toBe(true);
  });
});

describe('ariaCurrentFor', () => {
  it('distinguishes the page itself from a mapped list page', () => {
    expect(ariaCurrentFor('/news', {currentPath: '/news', isExact: true})).toBe('page');
    expect(ariaCurrentFor('/news', {currentPath: '/news', isExact: false})).toBe('true');
    expect(ariaCurrentFor('/about', {currentPath: '/news', isExact: true})).toBeUndefined();
    expect(ariaCurrentFor(null, {currentPath: '/news', isExact: true})).toBeUndefined();
  });
});

describe('sectionOptions', () => {
  it('lists the landing page first unless a child already links to it', () => {
    expect(sectionOptions(MENU[3]).map((option) => option.label)).toEqual([
      'Projects',
      'Current Projects',
      'Past Projects',
      'Project Submission',
      'Sample Proposals',
    ]);
    expect(sectionOptions(MENU[2]).map((option) => option.label)[0]).toBe('Event Info');
  });

  it('indents nested pages', () => {
    const nested = item('Section', '/section', [item('Child', '/child', [item('Grandchild', '/grandchild')])]);
    expect(sectionOptions(nested).map((option) => option.label)).toEqual(['Section', 'Child', '– Grandchild']);
  });
});
