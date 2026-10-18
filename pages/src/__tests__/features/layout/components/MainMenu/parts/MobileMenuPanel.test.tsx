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
  handlers?: {onAccountClick?: () => void; onLoginClick?: () => void; onLogoutClick?: () => void};
}

const Harness = ({
  menuItems = [],
  state = 'ready',
  hasMemberIdentity = false,
  user = null,
  current = null,
  initiallyOpen = false,
  handlers = {},
}: HarnessProps) => {
  const [open, setOpen] = useState(initiallyOpen);
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
    expect(dialog).toHaveClass('is-open');
    expect(trigger).toHaveAttribute('aria-expanded', 'true');
    await waitFor(() =>
      expect(screen.getByRole('link', {name: 'Innovate To Grow home'})).toHaveFocus(),
    );

    fireEvent.keyDown(document, {key: 'Escape'});
    expect(dialog).toHaveAttribute('hidden');
    expect(trigger).toHaveFocus();
    expect(trigger).toHaveAttribute('aria-expanded', 'false');
  });

  it('closes from its own close button in the repeated blue bar', () => {
    render(<Harness initiallyOpen />);
    const dialog = screen.getByRole('dialog', {name: 'Mobile menu'});

    fireEvent.click(within(dialog).getByRole('button', {name: 'Close menu'}));
    expect(dialog).toHaveAttribute('hidden');
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

  it('skips links of collapsed sections when wrapping focus', () => {
    render(<Harness initiallyOpen menuItems={[news, projects]} />);
    const dialog = screen.getByRole('dialog', {name: 'Mobile menu'});
    const give = within(dialog).getByRole('link', {name: 'Give'});

    // "Past Projects" sits in a collapsed (hidden) list, so it is not a Tab stop.
    const brand = within(dialog).getByRole('link', {name: 'Innovate To Grow home'});
    brand.focus();
    fireEvent.keyDown(document, {key: 'Tab', shiftKey: true});
    expect(give).toHaveFocus();
  });

  it('renders the menu as 48px rows with an expand button for sections', () => {
    render(<Harness initiallyOpen menuItems={[news, projects]} />);
    const dialog = screen.getByRole('dialog', {name: 'Mobile menu'});

    expect(within(dialog).getByRole('link', {name: 'News'})).toHaveAttribute('href', '/news');
    const expand = within(dialog).getByRole('button', {name: 'Projects pages'});
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
    const dialog = screen.getByRole('dialog', {name: 'Mobile menu'});

    expect(within(dialog).getByRole('button', {name: 'Projects pages'})).toHaveAttribute('aria-expanded', 'true');
    expect(within(dialog).getByRole('link', {name: 'Projects'})).toHaveAttribute('aria-current', 'true');
    expect(within(dialog).getByRole('link', {name: 'Current Projects'})).toHaveAttribute('aria-current', 'page');
    expect(within(dialog).getByRole('link', {name: 'News'})).not.toHaveAttribute('aria-current');
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
  });

  it('lists the UC Merced links at the bottom', () => {
    render(<Harness initiallyOpen />);
    const links = within(screen.getByRole('list', {name: 'UC Merced links'})).getAllByRole('link');
    expect(links.map((link) => link.textContent)).toEqual(['Directory', 'Apply', 'Give']);
    links.forEach((link) => expect(link).toHaveAttribute('target', '_blank'));
  });
});
