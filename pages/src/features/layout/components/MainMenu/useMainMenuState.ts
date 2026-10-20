import {useEffect, useMemo, useRef, useState} from 'react';
import {useMenu} from '../LayoutProvider/context';
import {useAuth} from '@/features/auth';
import {type MenuItem} from '@/features/layout/api';

const NO_MENU_ITEMS: MenuItem[] = [];

export const useMainMenuState = () => {
  const {menu, state} = useMenu();
  const {user, isAuthenticated, logout, refreshProfile} = useAuth();
  const [openItemIndex, setOpenItemIndex] = useState<number | null>(null);
  const [isMobileOpen, setIsMobileOpen] = useState(false);
  const [isMemberDropdownOpen, setIsMemberDropdownOpen] = useState(false);
  const hasSyncedMemberProfile = useRef(false);
  const prevLayoutStateRef = useRef<typeof state | undefined>(undefined);
  const introFadePlayedRef = useRef(false);
  const [navIntroFade, setNavIntroFade] = useState(false);
  const menuItems = useMemo(() => menu?.items ?? NO_MENU_ITEMS, [menu]);

  useEffect(() => {
    const handleToggle = () => setIsMobileOpen((prev) => !prev);
    window.addEventListener('toggle-menu', handleToggle);
    return () => window.removeEventListener('toggle-menu', handleToggle);
  }, []);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth > 992) setIsMobileOpen(false);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    if (!isAuthenticated) {
      hasSyncedMemberProfile.current = false;
      return;
    }
    if (!user?.profile_image && !hasSyncedMemberProfile.current) {
      hasSyncedMemberProfile.current = true;
      void refreshProfile();
    }
  }, [isAuthenticated, refreshProfile, user?.profile_image]);

  useEffect(() => {
    const prev = prevLayoutStateRef.current;
    prevLayoutStateRef.current = state;
    if (prev === undefined || introFadePlayedRef.current || prev !== 'loading' || state !== 'ready' || !menuItems.length) {
      return;
    }
    introFadePlayedRef.current = true;
    setTimeout(() => setNavIntroFade(true), 0);
  }, [menuItems.length, state]);

  useEffect(() => {
    document.body.style.overflow = isMobileOpen ? 'hidden' : '';
    // Lets page-level sheets hide floating widgets (the UserWay button) behind the open phone menu.
    document.documentElement.classList.toggle('is-mobile-menu-open', isMobileOpen);
    return () => {
      document.body.style.overflow = '';
      document.documentElement.classList.remove('is-mobile-menu-open');
    };
  }, [isMobileOpen]);

  return {
    isAuthenticated,
    // The header only shows who is signed in; it makes no protected decision. Gating it on
    // `isAuthenticated` flashes "Sign In" at a signed-in member for the whole background
    // check, and leaves the anonymous header up indefinitely if that check cannot complete.
    // A persisted identity is enough to render; protected routes still gate on the real flag.
    hasMemberIdentity: Boolean(user),
    isMemberDropdownOpen,
    isMobileOpen,
    logout,
    menuItems,
    navIntroFade,
    openItemIndex,
    setIsMemberDropdownOpen,
    setIsMobileOpen,
    setNavIntroFade,
    setOpenItemIndex,
    state,
    user,
  };
};
