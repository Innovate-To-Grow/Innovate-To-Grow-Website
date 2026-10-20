import {cleanup, fireEvent, render, screen} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';

import type {User} from '@/features/auth/api/types';
import {MemberMenu} from '@/features/layout/components/MainMenu/parts/MemberMenu';

afterEach(() => {
  cleanup();
});

const makeUser = (overrides: Partial<User> = {}): User => ({
  member_uuid: 'member-uuid',
  email: 'member@example.com',
  ...overrides,
});

const makeProps = (overrides: Record<string, unknown> = {}) => ({
  user: makeUser(),
  hasMemberIdentity: true,
  isOpen: false,
  onMouseEnter: vi.fn(),
  onMouseLeave: vi.fn(),
  onToggle: vi.fn(),
  onClose: vi.fn(),
  onAccountClick: vi.fn(),
  onLoginClick: vi.fn(),
  onLogoutClick: vi.fn(),
  ...overrides,
});

describe('MemberMenu', () => {
  it('shows an underlined "Sign in" link to /login for anonymous visitors', () => {
    const props = makeProps({user: null, hasMemberIdentity: false});
    render(<MemberMenu {...props} />);

    const link = screen.getByRole('link', {name: 'Sign in'});
    expect(link).toHaveAttribute('href', '/login');
    expect(link).toHaveClass('member-signin');

    fireEvent.click(link);
    expect(props.onLoginClick).toHaveBeenCalledTimes(1);
  });

  it('lets a modified click open /login natively instead of routing', () => {
    const props = makeProps({user: null, hasMemberIdentity: false});
    render(<MemberMenu {...props} />);

    fireEvent.click(screen.getByRole('link', {name: 'Sign in'}), {ctrlKey: true});
    expect(props.onLoginClick).not.toHaveBeenCalled();
  });

  it('renders the "My Account" menu button for a member, without an avatar by default', () => {
    render(<MemberMenu {...makeProps({user: makeUser()})} />);

    const button = screen.getByRole('button', {name: 'My Account'});
    expect(button).toHaveClass('member-button', 'authenticated');
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(document.querySelector('img.member-avatar')).toBeNull();
    expect(document.querySelector('.member-arrow')).not.toBeNull();
    // The identity is only listed inside the open menu.
    expect(screen.queryByText('member@example.com')).toBeNull();
  });

  it('renders the profile image when available', () => {
    const {container} = render(
      <MemberMenu {...makeProps({user: makeUser({profile_image: '/media/me.png'})})} />,
    );

    const img = container.querySelector('img.member-avatar');
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute('src', '/media/me.png');
  });

  it('lists who is signed in inside the open menu', () => {
    render(<MemberMenu {...makeProps({isOpen: true})} />);
    expect(screen.getByText('Signed in as')).toBeInTheDocument();
    expect(screen.getByText('member@example.com')).toHaveClass('member-name');
  });

  it('falls back to the formatted phone number when there is no email', () => {
    const user = makeUser({email: '', phone: '+12025550123'});
    render(<MemberMenu {...makeProps({user, isOpen: true})} />);

    expect(screen.getByText('(202) 555-0123')).toBeInTheDocument();
  });

  it('falls back to "Member" when there is no email or phone', () => {
    const user = makeUser({email: ''});
    render(<MemberMenu {...makeProps({user, isOpen: true})} />);

    expect(screen.getByText('Member')).toBeInTheDocument();
  });

  it('shows account and sign-out actions when the dropdown is open', () => {
    const props = makeProps({isOpen: true});
    render(<MemberMenu {...props} />);

    const account = screen.getByRole('button', {name: 'Account'});
    const signOut = screen.getByRole('button', {name: 'Sign Out'});

    fireEvent.click(account);
    expect(props.onAccountClick).toHaveBeenCalled();

    fireEvent.click(signOut);
    expect(props.onLogoutClick).toHaveBeenCalled();
  });

  it('applies the is-authenticated and is-open classes and toggles on click', () => {
    const props = makeProps({isOpen: true});
    const {container} = render(<MemberMenu {...props} />);

    expect(container.querySelector('.site-header-member')).toHaveClass(
      'is-authenticated',
      'is-open',
    );

    const button = screen.getByRole('button', {name: 'My Account'});
    expect(button).toHaveAttribute('aria-expanded', 'true');
    expect(button).toHaveAttribute('aria-controls', 'member-dropdown');
    fireEvent.click(button);
    expect(props.onToggle).toHaveBeenCalled();
  });

  it('closes on Escape and returns focus to the menu button', () => {
    const props = makeProps({isOpen: true});
    render(<MemberMenu {...props} />);

    const account = screen.getByRole('button', {name: 'Account'});
    account.focus();
    fireEvent.keyDown(account, {key: 'Escape'});

    expect(props.onClose).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', {name: 'My Account'})).toHaveFocus();
  });

  it('closes when focus leaves the member area', () => {
    const props = makeProps({isOpen: true});
    render(
      <>
        <MemberMenu {...props} />
        <button type="button">Elsewhere</button>
      </>,
    );

    fireEvent.blur(screen.getByRole('button', {name: 'Account'}), {
      relatedTarget: screen.getByRole('button', {name: 'Elsewhere'}),
    });
    expect(props.onClose).toHaveBeenCalledTimes(1);
  });

  it('keeps the menu open while focus moves inside it', () => {
    const props = makeProps({isOpen: true});
    render(<MemberMenu {...props} />);

    fireEvent.blur(screen.getByRole('button', {name: 'Account'}), {
      relatedTarget: screen.getByRole('button', {name: 'Sign Out'}),
    });
    expect(props.onClose).not.toHaveBeenCalled();
  });

  it('forwards mouse enter and leave handlers', () => {
    const props = makeProps({});
    const {container} = render(<MemberMenu {...props} />);
    const root = container.querySelector('.site-header-member') as HTMLElement;

    fireEvent.mouseEnter(root);
    expect(props.onMouseEnter).toHaveBeenCalled();

    fireEvent.mouseLeave(root);
    expect(props.onMouseLeave).toHaveBeenCalled();
  });
});
