import type {SVGProps} from 'react';

const PATHS: Record<string, string> = {
  'angle-down': 'm6 9 6 6 6-6',
  'angle-right': 'm9 6 6 6-6 6',
  'arrow-left': 'm10 6-6 6 6 6M4 12h16',
  'check-circle': 'M20 11a8 8 0 1 1-4-7M9 11l3 3 8-8',
  cog: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M4 12h2m12 0h2M12 4v2m0 12v2m-5.7-2.3 1.4-1.4m8.6-8.6 1.4-1.4m0 11.4-1.4-1.4M7.7 7.7 6.3 6.3',
  'exclamation-circle': 'M12 8v5m0 3h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  'exclamation-triangle': 'M10.3 3.7 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.7a2 2 0 0 0-3.4 0ZM12 9v4m0 4h.01',
  'info-circle': 'M12 11v6m0-9h.01M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0',
  lock: 'M6 10h12v10H6zM8 10V7a4 4 0 0 1 8 0v3',
  'sign-out': 'M10 5H5v14h5m4-3 4-4-4-4m4 4H9',
  times: 'M6 6l12 12M18 6 6 18',
  user: 'M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10',
  'user-circle': 'M20 21a8 8 0 0 0-16 0M12 13a4 4 0 1 0 0-8 4 4 0 0 0 0 8M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20',
};

function normalizeName(name: string): string {
  return name.split(/\s+/).find((part) => part.startsWith('fa-'))?.slice(3) ?? name.replace(/^fa-/, '');
}

export function Icon({name, className, ...props}: SVGProps<SVGSVGElement> & {name: string}) {
  const path = PATHS[normalizeName(name)] ?? 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20';
  // CMS-managed layout styles still use .fa for icon sizing and spacing.
  const classes = className ? `fa ${className}` : 'fa';

  return (
    <svg
      viewBox="0 0 24 24"
      width="1em"
      height="1em"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={classes}
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      <path d={path} />
    </svg>
  );
}
