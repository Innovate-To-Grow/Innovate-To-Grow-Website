import {useRef, useState} from 'react';
import {
  cleanup,
  fireEvent,
  render,
  screen,
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

  it('keeps the loop ends on controls that show, with a section collapsed or expanded', () => {
    render(<Harness initiallyOpen menuItems={[news, projects]} />);
    const panel = getPanel();
    const give = within(panel).getByRole('link', {name: 'Give'});
    const expand = within(panel).getByRole('button', {name: 'Projects pages'});

    // "Past Projects" sits in a collapsed (hidden) list, so it is not a Tab stop.
    const pastProjects = panel.querySelector('a[href="/past-projects"]') as HTMLElement;
    expect(pastProjects.closest('[hidden]')).not.toBeNull();
    getTrigger().focus();
    expect(pressTab(true)).toBe(false);
    expect(give).toHaveFocus();

    fireEvent.click(expand);
    expect(pastProjects.closest('[hidden]')).toBeNull();
    give.focus();
    expect(pressTab()).toBe(false);
    expect(getTrigger()).toHaveFocus();
  });

  it('starts the loop at the first panel control when there is no menu button', () => {
    render(<Harness initiallyOpen withTrigger={false} menuItems={[news]} />);
    const panel = getPanel();
    const newsLink = within(panel).getByRole('link', {name: 'News'});

    within(panel).getByRole('link', {name: 'Give'}).focus();
    expect(pressTab()).toBe(false);
    expect(newsLink).toHaveFocus();
  });

  it('leaves controls under a hidden ancestor out of the loop, parking focus on the panel when none is left', () => {
    // Every control sits under a hidden ancestor (as the links of a collapsed section do) and there is no
    // menu button, so nothing is left to Tab to.
    render(
      <div hidden>
        <Harness initiallyOpen withTrigger={false} />
      </div>,
    );
    const panel = getPanel();
    // jsdom will not move focus under a hidden ancestor, so watch the call itself.
    const focus = vi.spyOn(panel, 'focus');

    expect(pressTab()).toBe(false);
    expect(focus).toHaveBeenCalledTimes(1);
  });

  it('renders the menu as 48px rows with an expand button for sections', () => {
    render(<Harness initiallyOpen menuItems={[news, projects]} />);
    const panel = getPanel();

    expect(within(panel).getByRole('link', {name: 'News'})).toHaveAttribute('href', '/news');
    const expand = within(panel).getByRole('button', {name: 'Projects pages'});
    expect(expand).toHaveAttribute('aria-expanded', 'false');

    const list = document.getElementById(expand.getAttribute('aria-controls') ?? '');
    expect(list).toHaveAttribute('hidden');

    fireEvent.click(expand);
    expect(expand).toHaveAttribute('aria-expanded', 'true');
    expect(list).not.toHaveAttribute('hidden');
    expect(within(list as HTMLElement).getByRole('link', {name: 'Past Projects'})).toHaveAttribute(
      'href',
      '/past-projects',
    );
    // Opening a section is a tap inside the panel: it stays open.
    expect(panel).not.toHaveAttribute('hidden');

    fireEvent.click(expand);
    expect(expand).toHaveAttribute('aria-expanded', 'false');
  });

  it('starts with the current section expanded and marks the current page', () => {
    render(
      <Harness
        initiallyOpen
        menuItems={[news, projects]}
        current={{menuIndex: 1, currentPath: '/current-projects', isExact: true}}
      />,
    );
    const panel = getPanel();

    expect(within(panel).getByRole('button', {name: 'Projects pages'})).toHaveAttribute('aria-expanded', 'true');
    expect(within(panel).getByRole('link', {name: 'Projects'})).toHaveAttribute('aria-current', 'true');
    expect(within(panel).getByRole('link', {name: 'Current Projects'})).toHaveAttribute('aria-current', 'page');
    expect(within(panel).getByRole('link', {name: 'News'})).not.toHaveAttribute('aria-current');
  });

  it('shows a loading skeleton and an error message', () => {
    const {rerender} = render(<Harness initiallyOpen state="loading" />);
    const nav = screen.getByRole('navigation', {name: 'Mobile navigation'});
    expect(nav).toHaveAttribute('aria-busy', 'true');
    expect(nav.querySelectorAll('.header-mobile-nav-skeleton-row')).toHaveLength(7);

    rerender(<Harness initiallyOpen state="error" />);
    expect(screen.getByText('Menu unavailable')).toBeInTheDocument();
  });

  it('offers sign in to visitors and the account actions to members', () => {
    const onLoginClick = vi.fn();
    const {unmount} = render(<Harness initiallyOpen handlers={{onLoginClick}} />);
    fireEvent.click(screen.getByRole('button', {name: 'Sign In / Sign Up'}));
    expect(onLoginClick).toHaveBeenCalledTimes(1);
    unmount();

    const onAccountClick = vi.fn();
    const onLogoutClick = vi.fn();
    render(
      <Harness
        initiallyOpen
        hasMemberIdentity
        user={{member_uuid: 'm', email: 'member@example.com'}}
        handlers={{onAccountClick, onLogoutClick}}
      />,
    );
    const member = document.querySelector('.header-mobile-member') as HTMLElement;
    expect(member).toHaveTextContent('member@example.com');
    fireEvent.click(within(member).getByRole('button', {name: 'Account'}));
    fireEvent.click(within(member).getByRole('button', {name: 'Sign Out'}));
    expect(onAccountClick).toHaveBeenCalledTimes(1);
    expect(onLogoutClick).toHaveBeenCalledTimes(1);
    expect(member.querySelector('img')).toBeNull();
  });
});
