import {useEffect, useMemo, useRef, useState} from 'react';
import {useMenu} from '../LayoutProvider/context';
import {useAuth} from '../../Auth';
import {formatCurrentMenuDate} from './parts/shared';

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
  const currentDate = useMemo(formatCurrentMenuDate, []);
  const menuItems = menu?.items ?? [];

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
    return () => {
      document.body.style.overflow = '';
    };
  }, [isMobileOpen]);

  return {
    currentDate,
    isAuthenticated,
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
