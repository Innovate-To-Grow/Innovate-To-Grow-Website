import type {ComponentProps} from 'react';
import {act, cleanup, render} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {SaveControls} from '@/features/projects/components/search/controls/SearchTableToolbar';
import type {SearchTableSave} from '@/features/projects/components/search/state/useSearchTableSave';
import {shownText, translatePage} from '@/__tests__/features/projects/fixtures/pageTranslation';

const saveState = (isSaving: boolean) => ({isSaving, saveSelected: vi.fn()}) as unknown as SearchTableSave;

const controls = (overrides: Partial<ComponentProps<typeof SaveControls>> = {}) => (
  <SaveControls
    origin="top"
    save={saveState(false)}
    hasSelection
    selectedCount={3}
    hiddenSelectedCount={1}
    mergeDisabled={false}
    mergeLabel="Add to Curation"
    mergingVerb="Adding"
    selectionHintId="selection-hint"
    {...overrides}
  />
);

describe('SaveControls on a translated page', () => {
  afterEach(() => {
    cleanup();
  });

  it('keeps the button label and the selection count in step, and survives the hidden count going away', () => {
    const errors: unknown[] = [];
    const onError = (event: ErrorEvent) => {
      errors.push(event.error);
      event.preventDefault();
    };
    window.addEventListener('error', onError);
    const view = render(controls());
    // Chrome's Translate swaps the text nodes for its own elements, leaving React's detached.
    translatePage(view.container);
    try {
      act(() => view.rerender(controls({selectedCount: 1, hiddenSelectedCount: 0})));
      act(() => view.rerender(controls({save: saveState(true), selectedCount: 1, hiddenSelectedCount: 0})));
    } catch (error) {
      errors.push(error);
    }
    window.removeEventListener('error', onError);

    expect(errors).toEqual([]);
    expect(shownText(view.container.querySelector('.search-table-selection-count'))).toBe('1 selected');
    expect(shownText(view.container.querySelector('.search-table-save-button'))).toBe('Adding…');
  });

  it('shows the count beside the label and says how many checked rows the search hides', () => {
    const view = render(controls());

    expect(view.container.querySelector('.search-table-save-button')).toHaveTextContent(/^Add to Curation · 3$/);
    expect(view.container.querySelector('.search-table-selection-count')).toHaveTextContent(
      /^3 selected \(1 not shown by the current search\)$/,
    );
  });
});
