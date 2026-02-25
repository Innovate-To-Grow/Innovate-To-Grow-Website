import {useRef, useEffect} from 'react';

interface GrapesJSRendererProps {
    html: string;
    css: string;
    slug: string;
    className?: string;
}

/**
 * Scopes CSS selectors with a page-specific prefix to prevent style pollution.
 */
function scopeCSS(css: string, slug: string): string {
    if (!css) return '';
    const scopeClass = `.grapesjs-page-${slug.replace(/\//g, '-')}`;

    return css.replace(
        /([^{}@]+)(\{)/g,
        (_match: string, selector: string, brace: string) => {
            const trimmed = selector.trim();
            // Don't scope @-rules or empty selectors
            if (!trimmed || trimmed.startsWith('@')) {
                return selector + brace;
            }
            // Scope each comma-separated selector
            const scoped = trimmed
                .split(',')
                .map((s: string) => {
                    const t = s.trim();
                    if (!t) return t;
                    // body/html selectors get replaced with the scope class
                    if (t === 'body' || t === 'html') return scopeClass;
                    return `${scopeClass} ${t}`;
                })
                .join(', ');
            return scoped + brace;
        },
    );
}

/**
 * GrapesJSRenderer renders a page built with the GrapesJS editor.
 *
 * It injects scoped CSS and the raw HTML output from GrapesJS.
 * Dynamic data hydration will be added in Phase 2.
 */
export const GrapesJSRenderer = ({html, css, slug, className = ''}: GrapesJSRendererProps) => {
    const containerRef = useRef<HTMLDivElement>(null);
    const scopeClass = `grapesjs-page-${slug.replace(/\//g, '-')}`;

    // Future: dynamic data hydration hook (Phase 2)
    useEffect(() => {
        if (!containerRef.current) return;
        // Phase 2: hydrateDynamicElements(containerRef.current, dynamicConfig);
    }, [html]);

    return (
        <>
            {css && <style>{scopeCSS(css, slug)}</style>}
            <div
                ref={containerRef}
                className={`grapesjs-page ${scopeClass} ${className}`}
                dangerouslySetInnerHTML={{__html: html}}
            />
        </>
    );
};
