import {act, cleanup, fireEvent, render} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';
import {shownText, translatePage} from '@/__tests__/features/projects/fixtures/pageTranslation';

// On phones the saved list folds behind a toggle whose label changes when it opens. Chrome's Translate replaces the
// label's text node with its own elements; a label that was not its element's only child was then updated in the
// detached node, and the page kept saying "Show" on a list that was open.

vi.mock('@/features/auth', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/features/auth')>()),
  useAuth: () => ({isAuthenticated: true, user: null}),
}));

const row = (index: number): ProjectGridRow => ({
  semester_label: '2025-1 Spring',
  class_code: 'CAP',
  team_number: `${index}`,
  team_name: `Team ${index}`,
  project_title: `Project ${index}`,
  organization: 'Acme',
  industry: 'Energy',
  abstract: 'An abstract',
  student_names: 'Ada',
  is_presenting: '',
});

const items = createProjectGridItems([row(1), row(2)], 'translated');

const toggleOf = (container: HTMLElement) =>
  container.querySelector('.project-grid-phone-list-toggle') as HTMLButtonElement;

/** The toggle's labels, closed and open, as an untranslated page shows them. */
const untranslatedLabels = () => {
  const {container, unmount} = render(<MergedResultsTable rows={items} onCreateShare={vi.fn()} />);
  const toggle = toggleOf(container);
  const closed = toggle.textContent;
  fireEvent.click(toggle);
  const open = toggle.textContent;
  unmount();
  return {closed, open};
};

describe('MergedListGrid on a translated page', () => {
  afterEach(() => cleanup());

  it("updates the saved list's phone toggle when it opens and closes", () => {
    const labels = untranslatedLabels();
    expect(labels.open).not.toBe(labels.closed);

    const errors: unknown[] = [];
    const onError = (event: ErrorEvent) => {
      errors.push(event.error);
      event.preventDefault();
    };
    window.addEventListener('error', onError);
    try {
      const {container} = render(<MergedResultsTable rows={items} onCreateShare={vi.fn()} />);
      translatePage(container);
      const toggle = toggleOf(container);

      act(() => toggle.click());
      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      expect(shownText(toggle)).toBe(labels.open);

      act(() => toggle.click());
      expect(toggle).toHaveAttribute('aria-expanded', 'false');
      expect(shownText(toggle)).toBe(labels.closed);
    } finally {
      window.removeEventListener('error', onError);
    }
    expect(errors).toEqual([]);
  });
});
