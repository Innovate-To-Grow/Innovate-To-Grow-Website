import {useEffect, type RefObject} from 'react';

const FOCUSABLE_SELECTOR = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

const isVisible = (element: HTMLElement) => !element.closest('[hidden]');

/**
 * While ``isOpen``: focus the first control, keep Tab cycling through the menu button and the panel
 * (the page behind them is covered), close on Escape; on close, return focus to the menu button.
 */
export const useMenuFocusLoop = (
  panelRef: RefObject<HTMLDivElement | null>,
  isOpen: boolean,
  onClose: () => void,
  triggerRef: RefObject<HTMLButtonElement | null>,
) => {
  useEffect(() => {
    if (!isOpen) return;
    const panel = panelRef.current;
    if (!panel) return;
    const trigger = triggerRef.current;

    const animationFrame = window.requestAnimationFrame(() => {
      panel.querySelector<HTMLElement>(FOCUSABLE_SELECTOR)?.focus();
    });

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      // The menu button sits before the panel in the page, so it starts the loop.
      const focusable = [
        ...(trigger ? [trigger] : []),
        ...Array.from(panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(isVisible),
      ];
      if (!focusable.length) {
        event.preventDefault();
        panel.focus();
        return;
      }

      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      const inLoop = active === trigger || panel.contains(active);
      if (event.shiftKey && (active === first || !inLoop)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !inLoop)) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => {
      window.cancelAnimationFrame(animationFrame);
      document.removeEventListener('keydown', handleKeyDown);
      trigger?.focus();
    };
  }, [panelRef, isOpen, onClose, triggerRef]);
};
