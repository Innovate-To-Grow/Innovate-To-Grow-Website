import {cleanup, fireEvent, render, screen, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {PastProjectsBuilder} from '@/features/projects/components/curation/builder/composition/PastProjectsBuilder';
import {authenticatedAuth, getMergedSection, ROWS} from '@/__tests__/features/projects/components/curation/builder/composition/fixtures/pastProjectsBuilderFixtures';

const mockUseAuth = vi.fn();
const mockSearchPastProjectsWithAI = vi.fn();
const mockBuildLoginPath = vi.fn();
const mockHydrateProjectGridRowsSettled = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {
    ...actual,
    useAuth: () => mockUseAuth(),
  };
});

vi.mock('@/features/auth/api/navigation/redirects', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth/api/navigation/redirects')>();
  return {
    ...actual,
    buildLoginPath: (...args: unknown[]) => mockBuildLoginPath(...args),
  };
});

vi.mock('@/features/projects/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/projects/api')>();
  return {
    ...actual,
    searchPastProjectsWithAI: (...args: unknown[]) => mockSearchPastProjectsWithAI(...args),
    hydrateProjectGridRowsSettled: (...args: unknown[]) => mockHydrateProjectGridRowsSettled(...args),
  };
});

describe('PastProjectsBuilder — saving into the merged results', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue(authenticatedAuth);
    mockSearchPastProjectsWithAI.mockReset();
    mockBuildLoginPath.mockReset();
    mockHydrateProjectGridRowsSettled.mockReset();
    // The builder keeps its draft in localStorage; clear it so drafts don't leak between tests.
    localStorage.clear();
    sessionStorage.clear();
    vi.spyOn(window, 'confirm').mockImplementation(() => {
      throw new Error('Past projects should use an in-page confirmation dialog.');
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  describe('when the saved results change above the search tables', () => {
    let tops: number[];
    const scrollBy = vi.fn();

    beforeEach(() => {
      scrollBy.mockReset();
      vi.stubGlobal('scrollBy', scrollBy);
      tops = [];
      vi.spyOn(Element.prototype, 'getBoundingClientRect').mockImplementation(function (this: Element) {
        const top = this.hasAttribute('data-search-table-id') ? (tops.shift() ?? 300) : 0;
        return {top, bottom: top + 400, left: 0, right: 0, width: 0, height: 400, x: 0, y: top, toJSON: () => ({})} as DOMRect;
      });
    });

    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it('keeps the field the user is typing in where it is when the saved list grows above it', () => {
      const nameTops = [100, 186];
      vi.mocked(Element.prototype.getBoundingClientRect).mockImplementation(function (this: Element) {
        const top = this.matches('input[type="text"]')
          ? (nameTops.shift() ?? 186)
          : this.hasAttribute('data-search-table-id')
            ? (tops.shift() ?? 300)
            : 0;
        return {top, bottom: top + 40, left: 0, right: 0, width: 0, height: 40, x: 0, y: top, toJSON: () => ({})} as DOMRect;
      });
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
      fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));
      scrollBy.mockReset();

      screen.getByLabelText(/curation name/i).focus();
      fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));

      expect(getMergedSection()?.textContent).toContain('Bravo Project');
      expect(scrollBy).toHaveBeenCalledWith(0, 86);
    });

    it('leaves the page alone while the user is working in the saved results and nothing moves', () => {
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      const searchTable = screen.getByRole('heading', {level: 3, name: 'Search Table'}).closest('section') as HTMLElement;
      fireEvent.click(within(searchTable).getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));
      scrollBy.mockReset();

      screen.getByLabelText(/curation name/i).focus();
      tops = [120, 300];
      fireEvent.click(within(searchTable).getAllByLabelText('Select Bravo Project')[0]);
      fireEvent.click(within(searchTable).getByRole('button', {name: /add to curation/i}));

      expect(getMergedSection()?.textContent).toContain('Bravo Project');
      expect(scrollBy).not.toHaveBeenCalled();
    });

    it('does not pin a table that is off-screen', () => {
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);
      tops = [2000, 2800];
      fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));

      expect(getMergedSection()).not.toBeNull();
      expect(scrollBy).not.toHaveBeenCalled();
    });
  });

  it('takes the viewer and keyboard focus to the saved results', () => {
    const scrollIntoView = vi.fn();
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = scrollIntoView;
    try {
      render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

      fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
      fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
      fireEvent.click(screen.getByRole('button', {name: 'View Curation Draft'}));

      expect(scrollIntoView).toHaveBeenCalledWith(expect.objectContaining({block: 'start'}));
      expect(document.activeElement).toBe(screen.getByRole('heading', {level: 2, name: 'Curation Draft'}));
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it('removes multiple selected merged rows at once', async () => {
    render(<PastProjectsBuilder rows={ROWS} loading={false} error={null} onCreateShare={vi.fn()} />);

    fireEvent.click(screen.getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));
    fireEvent.click(screen.getAllByLabelText('Select Charlie Project')[0]);
    fireEvent.click(screen.getByRole('button', {name: /add to curation/i}));

    const merged = getMergedSection() as HTMLElement;
    expect(within(merged).getAllByText('Alpha Project').length).toBeGreaterThan(0);
    expect(within(merged).getAllByText('Charlie Project').length).toBeGreaterThan(0);

    fireEvent.click(within(merged).getAllByLabelText('Select Alpha Project')[0]);
    fireEvent.click(within(merged).getAllByLabelText('Select Charlie Project')[0]);
    fireEvent.click(within(merged).getByRole('button', {name: /remove selected/i}));

    expect(await screen.findByText('2 projects removed from the curation draft.')).toBeInTheDocument();
    expect(within(getMergedSection() as HTMLElement).queryByText('Alpha Project')).toBeNull();
  });
});
