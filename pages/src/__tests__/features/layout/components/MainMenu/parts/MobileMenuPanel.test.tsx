import {useRef, useState} from 'react';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {MobileMenuPanel} from '@/features/layout/components/MainMenu/parts/MobileMenuPanel';

const Harness = () => {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        Open navigation
      </button>
      <MobileMenuPanel
        menuItems={[]}
        state="ready"
        isMobileOpen={open}
        isAuthenticated={false}
        user={null}
        openItemIndex={null}
        triggerRef={triggerRef}
        onClose={() => setOpen(false)}
        onDesktopOpen={vi.fn()}
        onDesktopClose={vi.fn()}
        onDesktopToggle={vi.fn()}
        onAccountClick={vi.fn()}
        onLoginClick={vi.fn()}
        onLogoutClick={vi.fn()}
      />
    </>
  );
};

describe('MobileMenuPanel', () => {
  afterEach(cleanup);

  it('keeps the closed drawer hidden and inert, then restores focus on Escape', async () => {
    render(<Harness />);
    const trigger = screen.getByRole('button', {name: 'Open navigation'});
    const closedDialog = document.getElementById('mobile-menu');
    expect(closedDialog).not.toBeNull();
    expect(closedDialog).toHaveAttribute('hidden');
    expect(closedDialog).toHaveAttribute('inert');

    fireEvent.click(trigger);
    const dialog = screen.getByRole('dialog', {name: 'Mobile menu'});
    expect(dialog).not.toHaveAttribute('hidden');
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await waitFor(() =>
      expect(
        screen.getByRole('link', {name: /Innovate To Grow/i}),
      ).toHaveFocus(),
    );

    fireEvent.keyDown(document, {key: 'Escape'});
    expect(dialog).toHaveAttribute('hidden');
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('wraps Tab focus inside the open modal drawer', async () => {
    render(<Harness />);
    fireEvent.click(screen.getByRole('button', {name: 'Open navigation'}));
    const links = await screen.findAllByRole('link');
    const first = links[0];
    const last = links[links.length - 1];
    last.focus();

    fireEvent.keyDown(document, {key: 'Tab'});
    expect(first).toHaveFocus();

    first.focus();
    fireEvent.keyDown(document, {key: 'Tab', shiftKey: true});
    expect(last).toHaveFocus();
  });
});
