import {act, cleanup, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';

import {MergedResultsTable} from '@/features/projects/components/merged/composition/MergedResultsTable';
import {createProjectGridItems, type ProjectGridRow} from '@/features/projects/components/grid/contracts/projectGrid';

const mockUseAuth = vi.fn();

vi.mock('@/features/auth', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/features/auth')>();
  return {...actual, useAuth: () => mockUseAuth()};
});

const baseRow: ProjectGridRow = {
  semester_label: '2025-1 Spring',
  class_code: 'ENGR 120',
  team_number: 'T01',
  team_name: 'Team Alpha',
  project_title: 'Shared Project',
  organization: 'Acme',
  industry: 'Technology',
  abstract: 'A detailed project abstract.',
  student_names: 'Alice, Bob',
  is_presenting: '',
};

const makeItems = (rows: ProjectGridRow[] = [baseRow]) => createProjectGridItems(rows, 'test');

// The shared page's link panel: the shareable link, Copy Link, and the panel's own status line for the copy.
describe('MergedResultsTable in shared mode: the shareable link', () => {
  beforeEach(() => {
    mockUseAuth.mockReset();
    mockUseAuth.mockReturnValue({isAuthenticated: true});
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('copies the shareable link with the Copy Link button and says so in the panel, in the success colour', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    try {
      const {container} = render(<MergedResultsTable rows={makeItems()} sharedMode />);
      const panel = container.querySelector('.project-grid-share-result') as HTMLElement;

      fireEvent.click(within(panel).getByRole('button', {name: 'Copy Link'}));

      await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.href));
      // The panel's own status line, not the list's (the page has both).
      const line = await within(panel).findByText('Shareable URL copied.');
      expect(line).toHaveAttribute('role', 'status');
      expect(line).toHaveClass('project-grid-share-copy-status', 'itg-success');
      expect(line).not.toHaveClass('itg-error');
      expect(container.querySelector('.project-grid-status')).toBeEmptyDOMElement();
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('keeps the copy status line in the page while empty, and empties it again after four seconds', async () => {
    vi.useFakeTimers();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    try {
      const {container} = render(<MergedResultsTable rows={makeItems()} sharedMode />);
      const line = container.querySelector('.project-grid-share-result .project-grid-share-copy-status') as HTMLElement;
      expect(line).toHaveAttribute('role', 'status');
      expect(line).toBeEmptyDOMElement();

      await act(async () => {
        fireEvent.click(screen.getByRole('button', {name: 'Copy Link'}));
      });
      expect(line).toHaveTextContent('Shareable URL copied.');

      act(() => {
        vi.advanceTimersByTime(3999);
      });
      expect(line).toHaveTextContent('Shareable URL copied.');
      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(line).toBeEmptyDOMElement();
    } finally {
      vi.useRealTimers();
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('confirms when the shareable URL is copied to the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    try {
      render(<MergedResultsTable rows={makeItems()} sharedMode />);

      fireEvent.click(screen.getByLabelText('Shareable link'));

      await waitFor(() => expect(writeText).toHaveBeenCalledWith(window.location.href));
      expect(await screen.findByText('Shareable URL copied.')).toBeInTheDocument();
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    }
  });

  it('asks for a manual copy when no clipboard mechanism is available', async () => {
    // jsdom has neither navigator.clipboard nor document.execCommand — both paths fall through.
    render(<MergedResultsTable rows={makeItems()} sharedMode />);

    fireEvent.click(screen.getByLabelText('Shareable link'));

    expect(await screen.findByText('Unable to copy URL. Select the link and copy it manually.')).toHaveClass(
      'project-grid-share-copy-status',
      'itg-error',
    );
  });

  it('leaves the whole link selected for a manual copy when Copy Link fails', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('denied'));
    const execCommand = vi.fn().mockReturnValue(false);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    Object.defineProperty(document, 'execCommand', {value: execCommand, configurable: true, writable: true});
    try {
      render(<MergedResultsTable rows={makeItems()} sharedMode />);
      const input = screen.getByLabelText<HTMLInputElement>('Shareable link');

      fireEvent.click(screen.getByRole('button', {name: 'Copy Link'}));

      const line = await screen.findByText('Unable to copy URL. Select the link and copy it manually.');
      expect(line).toHaveClass('itg-error');
      expect(line).not.toHaveClass('itg-success');
      expect(execCommand).toHaveBeenCalledWith('copy');
      expect(input.selectionStart).toBe(0);
      expect(input.selectionEnd).toBe(window.location.href.length);
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
      Reflect.deleteProperty(document, 'execCommand');
    }
  });

  it('copies the share URL via document.execCommand when no async clipboard exists', async () => {
    Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, 'execCommand', {value: execCommand, configurable: true, writable: true});
    try {
      render(<MergedResultsTable rows={makeItems()} sharedMode />);

      fireEvent.click(screen.getByLabelText('Shareable link'));

      expect(await screen.findByText('Shareable URL copied.')).toBeInTheDocument();
      expect(execCommand).toHaveBeenCalledWith('copy');
    } finally {
      Object.defineProperty(document, 'execCommand', {value: undefined, configurable: true, writable: true});
    }
  });

  it('selects the share URL when the input takes focus, without touching the clipboard', async () => {
    // Tabbing onto the field used to copy, replacing whatever a keyboard user had on their clipboard.
    const writeText = vi.fn().mockResolvedValue(undefined);
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(window.navigator, 'clipboard', {value: {writeText}, configurable: true});
    Object.defineProperty(document, 'execCommand', {value: execCommand, configurable: true});
    try {
      render(<MergedResultsTable rows={makeItems()} sharedMode />);
      const input = screen.getByLabelText<HTMLInputElement>('Shareable link');

      input.focus();
      await act(async () => {});

      expect(input).toHaveFocus();
      expect(input.selectionStart).toBe(0);
      expect(input.selectionEnd).toBe(window.location.href.length);
      expect(writeText).not.toHaveBeenCalled();
      expect(execCommand).not.toHaveBeenCalled();
      expect(screen.queryByText('Shareable URL copied.')).toBeNull();
    } finally {
      Object.defineProperty(window.navigator, 'clipboard', {value: undefined, configurable: true});
      Reflect.deleteProperty(document, 'execCommand');
    }
  });
});
