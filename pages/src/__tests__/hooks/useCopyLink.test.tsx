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

const copyAndReport = async () => {
  const hook = renderHook(() => useCopyLink(MESSAGES));
  await act(() => hook.result.current.copy(URL_TO_COPY));
  return hook;
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

  describe('tone', () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    it('starts empty', () => {
      const {result} = renderHook(() => useCopyLink(MESSAGES));

      expect(result.current.status).toBe('');
      expect(result.current.tone).toBe('');
    });

    it('is success after a copy that worked', async () => {
      setClipboard(vi.fn().mockResolvedValue(undefined));

      const {result} = await copyAndReport();

      expect(result.current).toMatchObject({status: 'Link copied.', tone: 'success'});
    });

    it('is error when the Clipboard API rejects and copying by selection fails too', async () => {
      setClipboard(vi.fn().mockRejectedValue(new DOMException('Blocked by permissions policy', 'NotAllowedError')));
      setExecCommand(vi.fn().mockReturnValue(false));

      const {result} = await copyAndReport();

      expect(result.current).toMatchObject({status: 'Could not copy the link.', tone: 'error'});
    });

    it('clears together with the message after four seconds', async () => {
      vi.useFakeTimers();
      setClipboard(vi.fn().mockResolvedValue(undefined));
      const {result} = await copyAndReport();

      act(() => {
        vi.advanceTimersByTime(3999);
      });
      expect(result.current).toMatchObject({status: 'Link copied.', tone: 'success'});

      act(() => {
        vi.advanceTimersByTime(1);
      });
      expect(result.current).toMatchObject({status: '', tone: ''});
    });

    it('follows the latest copy, and a later copy restarts the four seconds', async () => {
      vi.useFakeTimers();
      const writeText = vi.fn().mockResolvedValue(undefined);
      setClipboard(writeText);
      const {result} = await copyAndReport();

      act(() => {
        vi.advanceTimersByTime(3000);
      });
      writeText.mockRejectedValue(new Error('denied'));
      setExecCommand(vi.fn().mockReturnValue(false));
      await act(() => result.current.copy(URL_TO_COPY));
      expect(result.current).toMatchObject({status: 'Could not copy the link.', tone: 'error'});

      act(() => {
        vi.advanceTimersByTime(3000);
      });
      expect(result.current.tone).toBe('error');
      act(() => {
        vi.advanceTimersByTime(1000);
      });
      expect(result.current).toMatchObject({status: '', tone: ''});
    });
  });
});
