import {act, renderHook} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import {useCopyLink} from '@/hooks/useCopyLink';

const MESSAGES = {copied: 'Link copied.', failed: 'Could not copy the link.'};
const URL_TO_COPY = 'https://i2g.ucmerced.edu/past-projects/project/abc';

const setClipboard = (writeText: ((text: string) => Promise<void>) | undefined) =>
  Object.defineProperty(window.navigator, 'clipboard', {configurable: true, value: writeText ? {writeText} : undefined});

const setExecCommand = (execCommand: ((command: string) => boolean) | undefined) =>
  Object.defineProperty(document, 'execCommand', {configurable: true, writable: true, value: execCommand});

const copyWithHook = async () => {
  const {result} = renderHook(() => useCopyLink(MESSAGES));
  await act(() => result.current.copy(URL_TO_COPY));
  return result.current.status;
};

describe('useCopyLink', () => {
  afterEach(() => {
    setClipboard(undefined);
    setExecCommand(undefined);
    vi.restoreAllMocks();
  });

  it('copies through the Clipboard API', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    setClipboard(writeText);

    expect(await copyWithHook()).toBe('Link copied.');
    expect(writeText).toHaveBeenCalledWith(URL_TO_COPY);
  });

  it('falls back to copying a selected field when the Clipboard API is denied (a cross-origin embed)', async () => {
    setClipboard(vi.fn().mockRejectedValue(new DOMException('Blocked by permissions policy', 'NotAllowedError')));
    const button = document.createElement('button');
    document.body.appendChild(button);
    button.focus();
    let copiedText: string | null = null;
    setExecCommand(
      vi.fn((command: string) => {
        const field = document.activeElement as HTMLTextAreaElement;
        copiedText = field.value.slice(field.selectionStart, field.selectionEnd);
        return command === 'copy';
      }),
    );

    expect(await copyWithHook()).toBe('Link copied.');
    expect(copiedText).toBe(URL_TO_COPY);
    expect(document.querySelector('textarea')).toBeNull();
    expect(document.activeElement).toBe(button);
    button.remove();
  });

  it('reports the failure when neither way copies', async () => {
    setClipboard(vi.fn().mockRejectedValue(new Error('denied')));
    setExecCommand(vi.fn().mockReturnValue(false));

    expect(await copyWithHook()).toBe('Could not copy the link.');
  });

  it('reports the failure when the browser has no way to copy', async () => {
    expect(await copyWithHook()).toBe('Could not copy the link.');
  });
});
