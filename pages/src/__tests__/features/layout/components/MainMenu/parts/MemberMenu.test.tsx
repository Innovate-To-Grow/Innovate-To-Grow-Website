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
  isAuthenticated: true,
  isOpen: false,
  onMouseEnter: vi.fn(),
  onMouseLeave: vi.fn(),
  onToggle: vi.fn(),
  onAccountClick: vi.fn(),
  onLoginClick: vi.fn(),
  onLogoutClick: vi.fn(),
  ...overrides,
});

describe('MemberMenu', () => {
  it('shows a sign-in button for anonymous visitors', () => {
    const props = makeProps({user: null, isAuthenticated: false});
    render(<MemberMenu {...props} />);

    const button = screen.getByRole('button', {name: 'Sign In'});
    expect(button).toHaveClass('member-button');
    expect(button).not.toHaveClass('authenticated');

    fireEvent.click(button);
    expect(props.onLoginClick).toHaveBeenCalled();
  });

  it('renders an authenticated member with a fallback icon and their email', () => {
    render(<MemberMenu {...makeProps({user: makeUser()})} />);

    const button = screen.getByRole('button', {name: 'member@example.com'});
    expect(button).toHaveClass('member-button', 'authenticated');
    expect(button).toHaveAttribute('aria-expanded', 'false');
    expect(document.querySelector('img.member-avatar')).toBeNull();
    expect(document.querySelector('.member-arrow')).not.toBeNull();
  });

  it('renders the profile image when available', () => {
    const {container} = render(
      <MemberMenu {...makeProps({user: makeUser({profile_image: '/media/me.png'})})} />,
    );

    const img = container.querySelector('img.member-avatar');
    expect(img).not.toBeNull();
    expect(img).toHaveAttribute('src', '/media/me.png');
  });

  it('falls back to the formatted phone number when there is no email', () => {
    const user = makeUser({email: '', phone: '+12025550123'});
    render(<MemberMenu {...makeProps({user})} />);

    expect(
      screen.getByRole('button', {name: '(202)555-0123'}),
    ).toBeInTheDocument();
  });

  it('falls back to "Member" when there is no email or phone', () => {
    const user = makeUser({email: ''});
    render(<MemberMenu {...makeProps({user})} />);

    expect(screen.getByRole('button', {name: 'Member'})).toBeInTheDocument();
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

    const button = screen.getByRole('button', {name: 'member@example.com'});
    expect(button).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(button);
    expect(props.onToggle).toHaveBeenCalled();
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
