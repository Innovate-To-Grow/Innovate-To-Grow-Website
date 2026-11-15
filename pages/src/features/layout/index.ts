// Layout components - unified exports (the components/ folder holds only component folders)
export { Footer } from './components/Footer/Footer';
export { MainMenu } from './components/MainMenu/menu/MainMenu';
export { Container } from './components/Container/Container';

// Re-export Container as Layout for backward compatibility
export { Container as Layout } from './components/Container/Container';

// Layout context provider and hooks
export { LayoutProvider } from './components/LayoutProvider/LayoutProvider';
export { useLayout, useMenu, useFooter } from './components/LayoutProvider/context';

export * from './api';
export {resolveSection, type SectionMatch} from './components/MainMenu/parts/sections';
export {useCurrentPathname, ROUTE_CHANGE_EVENT} from './hooks/useCurrentPathname';
export {useMediaQuery} from './hooks/useMediaQuery';
