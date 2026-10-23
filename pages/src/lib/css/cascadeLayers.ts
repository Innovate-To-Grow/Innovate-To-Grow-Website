// The bundled stylesheets sit in the itg.components cascade layer (src/styles/layers.css).
// A <style> added at runtime would otherwise be unlayered and beat every layered rule,
// whatever its specificity; in the same layer it keeps today's order: it loads last.
export const COMPONENTS_LAYER = 'itg.components';

export const inComponentsLayer = (css: string): string => `@layer ${COMPONENTS_LAYER} {\n${css}\n}`;
