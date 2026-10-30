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
import type {User} from '@/features/auth/api/types';
import type {MenuItem} from '@/features/layout/api';
import type {LayoutLoadState} from '@/features/layout/components/LayoutProvider/context';
import {MobileMenuPanel} from '@/features/layout/components/MainMenu/parts/MobileMenuPanel';

const projects: MenuItem = {
  title: 'Projects',
  url: '/projects',
  type: 'app',
  open_in_new_tab: false,
  children: [
    {title: 'Current Projects', url: '/current-projects', type: 'app', open_in_new_tab: false, children: []},
    {title: 'Past Projects', url: '/past-projects', type: 'app', open_in_new_tab: false, children: []},
  ],
};

const news: MenuItem = {title: 'News', url: '/news', type: 'app', open_in_new_tab: false, children: []};

interface HarnessProps {
  menuItems?: MenuItem[];
  state?: LayoutLoadState;
  hasMemberIdentity?: boolean;
  user?: User | null;
  current?: {menuIndex: number | null; currentPath: string; isExact: boolean} | null;
  initiallyOpen?: boolean;
  withTrigger?: boolean;
  handlers?: {onAccountClick?: () => void; onLoginClick?: () => void; onLogoutClick?: () => void};
}

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

const getPanel = () => document.getElementById('mobile-menu') as HTMLElement;
const getTrigger = () => screen.getByRole('button', {name: 'Toggle menu'});

/** Presses Tab (or Shift+Tab); true when the keypress was left to the browser's own focus move. */
const pressTab = (shiftKey = false) => fireEvent.keyDown(document, {key: 'Tab', shiftKey});

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

  it("shows the member's profile image when there is one", () => {
    render(
      <Harness
        initiallyOpen
        hasMemberIdentity
        user={{member_uuid: 'm', email: 'member@example.com', profile_image: 'https://example.com/me.png'}}
      />,
    );
    const avatar = document.querySelector('.header-mobile-member-info img') as HTMLImageElement;
    expect(avatar).toHaveClass('header-mobile-member-avatar');
    expect(avatar).toHaveAttribute('src', 'https://example.com/me.png');
    expect(avatar).toHaveAttribute('alt', '');
  });

  it('lists the UC Merced links at the bottom', () => {
    render(<Harness initiallyOpen />);
    const links = within(screen.getByRole('list', {name: 'UC Merced links'})).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual(['Directory', 'Apply', 'Give']);
    links.forEach((link) => expect(link).toHaveAttribute('target', '_blank'));
  });
});
