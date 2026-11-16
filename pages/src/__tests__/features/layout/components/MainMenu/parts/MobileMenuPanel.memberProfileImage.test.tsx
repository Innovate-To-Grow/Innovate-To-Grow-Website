import {useRef, useState} from 'react';
import {
  cleanup,
  render,
  screen,
  within,
} from '@testing-library/react';
import {afterEach, describe, expect, it, vi} from 'vitest';
import {MobileMenuPanel} from '@/features/layout/components/MainMenu/parts/MobileMenuPanel';
import {type HarnessProps} from '@/__tests__/features/layout/components/MainMenu/parts/mobileMenuPanelFixtures';

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
