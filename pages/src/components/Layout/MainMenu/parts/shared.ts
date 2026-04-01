import {type MenuItem} from '../../../../features/layout/api';

export const buildHref = (item: MenuItem) => item.url || '#';

/** Placeholder widths (px) for loading skeleton — similar footprint to real nav labels */
export const MENU_BAR_SKELETON_WIDTHS_PX = [56, 72, 64, 48, 80, 68, 52] as const;

export const formatCurrentMenuDate = () => {
  const date = new Date();
  const days = ['SUNDAY', 'MONDAY', 'TUESDAY', 'WEDNESDAY', 'THURSDAY', 'FRIDAY', 'SATURDAY'];
  const months = [
    'JANUARY', 'FEBRUARY', 'MARCH', 'APRIL', 'MAY', 'JUNE',
    'JULY', 'AUGUST', 'SEPTEMBER', 'OCTOBER', 'NOVEMBER', 'DECEMBER',
  ];
  return `${days[date.getDay()]} ${date.getDate()} ${months[date.getMonth()]} ${date.getFullYear()}`;
};
