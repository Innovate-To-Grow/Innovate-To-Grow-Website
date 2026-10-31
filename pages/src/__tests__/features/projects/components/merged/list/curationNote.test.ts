import {afterEach, describe, expect, it} from 'vitest';

import type {ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {
  builderExportTarget,
  currentLoginPath,
  sharedListExportTarget,
  signInToSave,
} from '@/features/projects/components/merged/list/curationNote';

const ID_A = '11111111-1111-4111-8111-111111111111';
const ID_B = '22222222-2222-4222-8222-222222222222';

const makeRow = (overrides: Partial<ProjectGridRow>): ProjectGridRow => ({
  semester_label: '2025 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'CAP-101',
  project_title: 'Solar Project',
  organization: 'Acme',
  industry: 'Energy',
  abstract: 'Abstract-101',
  student_names: 'Ada',
  is_presenting: '',
  ...overrides,
});

const ARCHIVE_ROW = makeRow({id: ID_A, catalog: 'archive'});
const CURRENT_ROW = makeRow({id: ID_B, semester_label: '2026 Fall', catalog: 'current', is_presenting: 'Yes'});

const login = (returnTo: string) => `/login?returnTo=${encodeURIComponent(returnTo)}`;

describe('signing in to save', () => {
  afterEach(() => window.history.replaceState(null, '', '/'));

  it('returns to the page itself on the site', () => {
    window.history.replaceState(null, '', '/all-projects?value=solar');

    expect(currentLoginPath('/all-projects')).toBe(login('/all-projects?value=solar'));
    expect(signInToSave([ARCHIVE_ROW], '/all-projects')).toEqual({
      href: login('/all-projects?value=solar'),
      inNewTab: false,
    });
  });

  it("goes from the widget to the builder page it is (All Projects), never back to the widget's frame", () => {
    window.history.replaceState(null, '', '/_embed/partner-all');

    expect(currentLoginPath('/all-projects')).toBe(login('/all-projects'));
    expect(signInToSave([ARCHIVE_ROW, CURRENT_ROW], '/all-projects')).toEqual({
      href: `/all-projects#curation-draft=${ID_A},${ID_B}`,
      inNewTab: true,
    });
  });

  it('goes from the widget to Past Projects when no path is given', () => {
    window.history.replaceState(null, '', '/_embed/partner-past');

    expect(currentLoginPath()).toBe(login('/past-projects'));
    expect(signInToSave([ARCHIVE_ROW])).toEqual({href: `/past-projects#curation-draft=${ID_A}`, inNewTab: true});
  });
});

describe('export targets', () => {
  const draft = {enabled: true, nameDraft: 'Spring picks', noteDraft: '<p>Hello</p>'};
  const shared = {enabled: false, titleDraft: '', noteDraft: '', savedNoteHtml: '<p>Saved</p>'};

  it('name an export with a current-semester project after All Projects', () => {
    expect(builderExportTarget('Curation Draft', draft, [ARCHIVE_ROW, CURRENT_ROW])).toEqual({
      fileBaseName: 'projects-spring-picks',
      context: {title: 'Spring picks', note: '<p>Hello</p>', heading: 'Innovate to Grow Projects'},
    });
    const unnamed = builderExportTarget('Curation Draft', {...draft, nameDraft: ''}, [CURRENT_ROW]);
    expect(unnamed.fileBaseName).toBe('projects');
    expect(sharedListExportTarget('Fall picks', shared, [CURRENT_ROW])).toEqual({
      fileBaseName: 'projects-fall-picks',
      context: {title: 'Fall picks', note: '<p>Saved</p>', heading: 'Innovate to Grow Projects'},
    });
  });

  it("keep an archive-only export's Past Projects file name and the exporters' own heading", () => {
    const builderTarget = builderExportTarget('Curation Draft', draft, [ARCHIVE_ROW]);
    const sharedTarget = sharedListExportTarget('Fall picks', shared, [ARCHIVE_ROW]);

    expect(builderTarget.fileBaseName).toBe('past-projects-spring-picks');
    expect(sharedTarget.fileBaseName).toBe('past-projects-fall-picks');
    expect(builderTarget.context.heading).toBeUndefined();
    expect(sharedTarget.context.heading).toBeUndefined();
  });
});
