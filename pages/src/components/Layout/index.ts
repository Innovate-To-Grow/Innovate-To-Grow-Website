// Layout components - unified exports
export { Footer } from './Footer/Footer';
export { MainMenu } from './MainMenu/MainMenu';
export { Container } from './Container/Container';

// Re-export Container as Layout for backward compatibility
export { Container as Layout } from './Container/Container';

// Layout context provider and hooks
export { LayoutProvider, useLayout, useMenu, useFooter } from './LayoutProvider/LayoutProvider';
