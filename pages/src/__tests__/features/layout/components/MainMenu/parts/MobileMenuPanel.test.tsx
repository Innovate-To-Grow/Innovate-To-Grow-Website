import {useRef, useState} from 'react';
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {MobileMenuPanel} from '@/features/layout/components/MainMenu/parts/MobileMenuPanel';
import {getPanel, getTrigger, type HarnessProps, news, pressTab, projects} from '@/__tests__/features/layout/components/MainMenu/parts/mobileMenuPanelFixtures';

/** The panel with the page's own menu button in front of it, toggling it as the header's button does. */
const Harness = ({
  menuItems = [],
  state = 'ready',
  hasMemberIdentity = false,
  user = null,
  current = null,
  initiallyOpen = false,
  withTrigger = true,
  handlers = {},
}: HarnessProps) => {
  const [open, setOpen] = useState(initiallyOpen);
  const triggerRef = useRef<HTMLButtonElement>(null);
  return (
    <>
      {withTrigger ? (
        <button
          ref={triggerRef}
          type="button"
          aria-label="Toggle menu"
          aria-controls="mobile-menu"
          aria-expanded={open}
          onClick={() => setOpen((prev) => !prev)}
        />
      ) : null}
      <MobileMenuPanel
        menuItems={menuItems}
        state={state}
        isMobileOpen={open}
        hasMemberIdentity={hasMemberIdentity}
        user={user}
        current={current}
        triggerRef={triggerRef}
        onClose={() => setOpen(false)}
        onAccountClick={handlers.onAccountClick ?? vi.fn()}
        onLoginClick={handlers.onLoginClick ?? vi.fn()}
        onLogoutClick={handlers.onLogoutClick ?? vi.fn()}
      />
    </>
  );
};

describe('MobileMenuPanel', () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it('keeps the closed panel hidden and inert, then restores focus to the menu button on Escape', async () => {
    render(<Harness menuItems={[news, projects]} />);
    const trigger = getTrigger();
    const panel = getPanel();
    expect(panel).not.toBeNull();
    expect(panel).toHaveAttribute('hidden');
    expect(panel).toHaveAttribute('inert');
    expect(panel).toHaveAttribute('aria-hidden', 'true');
    expect(panel).toHaveAttribute('tabindex', '-1');

    fireEvent.click(trigger);
    expect(panel).not.toHaveAttribute('hidden');
    expect(panel).not.toHaveAttribute('inert');
    expect(panel).toHaveAttribute('aria-hidden', 'false');
    expect(panel).toHaveClass('is-open');
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    // The first control inside the panel takes focus once it is on screen.
    await waitFor(() => expect(within(panel).getByRole('link', {name: 'News'})).toHaveFocus());

    // Other keys are left alone.
    expect(fireEvent.keyDown(document, {key: 'ArrowDown'})).toBe(true);
    expect(panel).not.toHaveAttribute('hidden');

    expect(fireEvent.keyDown(document, {key: 'Escape'})).toBe(false);
    expect(panel).toHaveAttribute('hidden');
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('is a "Mobile menu" region, not a modal dialog of its own', () => {
    render(<Harness />);
    const panel = getPanel();
    // Closed, it is out of the accessibility tree.
    expect(screen.queryByRole('region', {name: 'Mobile menu'})).toBeNull();

    fireEvent.click(getTrigger());
    expect(screen.getByRole('region', {name: 'Mobile menu'})).toBe(panel);
    expect(panel).toHaveAttribute('role', 'region');
    expect(panel).toHaveAttribute('aria-label', 'Mobile menu');
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(panel).not.toHaveAttribute('aria-modal');
  });

  it('leaves the blue bar and the site name to the page: no copy, close button or site-name row inside', () => {
    render(<Harness initiallyOpen menuItems={[news]} />);
    const panel = getPanel();

    expect(within(panel).queryByRole('button', {name: 'Close menu'})).toBeNull();
    expect(within(panel).queryByRole('link', {name: 'Innovate To Grow home'})).toBeNull();
    expect(within(panel).queryByText('Innovate To Grow')).toBeNull();
    expect(panel.querySelector('.header-mobile-top, .header-mobile-ucm, .header-mobile-sitename')).toBeNull();
    // The menu rows come first.
    expect(panel.firstElementChild).toBe(within(panel).getByRole('navigation', {name: 'Mobile navigation'}));
  });

  it('closes from the page menu button, which stays the open/close control, and keeps focus on it', async () => {
    render(<Harness menuItems={[news]} />);
    const trigger = getTrigger();
    fireEvent.click(trigger);
    await waitFor(() => expect(screen.getByRole('link', {name: 'News'})).toHaveFocus());

    trigger.focus();
    fireEvent.click(trigger);
    expect(getPanel()).toHaveAttribute('hidden');
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes on a tap on the dimmed backdrop, but not on a tap inside its sections', () => {
    const onLoginClick = vi.fn();
    render(<Harness initiallyOpen menuItems={[news]} handlers={{onLoginClick}} />);
    const panel = getPanel();

    fireEvent.click(within(panel).getByRole('navigation', {name: 'Mobile navigation'}));
    fireEvent.click(panel.querySelector('.header-mobile-member') as HTMLElement);
    fireEvent.click(within(panel).getByRole('button', {name: 'Sign In / Sign Up'}));
    expect(onLoginClick).toHaveBeenCalledTimes(1);
    expect(panel).not.toHaveAttribute('hidden');

    // The panel's own box shows only where the sections end: the backdrop.
    fireEvent.click(panel);
    expect(panel).toHaveAttribute('hidden');
    expect(getTrigger()).toHaveFocus();
  });

  it('loops Tab from the last panel control to the menu button, and Shift+Tab from the button to the last control', () => {
    render(<Harness initiallyOpen menuItems={[news, projects]} />);
    const panel = getPanel();
    const trigger = getTrigger();
    const give = within(panel).getByRole('link', {name: 'Give'});

    give.focus();
    expect(pressTab()).toBe(false);
    expect(trigger).toHaveFocus();

    // From the menu button the browser moves on into the panel, which follows it in the page.
    expect(pressTab()).toBe(true);
    expect(trigger).toHaveFocus();

    expect(pressTab(true)).toBe(false);
    expect(give).toHaveFocus();
  });

  it('leaves Tab between controls in the middle of the loop to the browser', () => {
    render(<Harness initiallyOpen menuItems={[news, projects]} />);
    const panel = getPanel();
    const newsLink = within(panel).getByRole('link', {name: 'News'});

    newsLink.focus();
    expect(pressTab()).toBe(true);
    expect(pressTab(true)).toBe(true);
    expect(newsLink).toHaveFocus();
  });

  it('pulls focus that is outside the loop back in, at either end', () => {
    const outside = document.createElement('button');
    outside.textContent = 'Behind the menu';
    document.body.appendChild(outside);
    try {
      render(<Harness initiallyOpen menuItems={[news]} />);
      const give = within(getPanel()).getByRole('link', {name: 'Give'});

      outside.focus();
      expect(pressTab()).toBe(false);
      expect(getTrigger()).toHaveFocus();

      outside.focus();
      expect(pressTab(true)).toBe(false);
      expect(give).toHaveFocus();
    } finally {
      outside.remove();
    }
  });
});
