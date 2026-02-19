import { useEffect, useRef, useCallback } from 'react';
import type { PageComponent } from '../../services/api';
import { GoogleSheetTable } from './GoogleSheetTable';

interface ComponentRendererProps {
  component: PageComponent;
  className?: string;
}

/**
 * ComponentRenderer renders a PageComponent with its HTML, CSS, and JS.
 * JavaScript is executed in an isolated scope using a sandboxed iframe.
 */
export const ComponentRenderer = ({ component, className = '' }: ComponentRendererProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const isHtmlLike = component.component_type === 'html' || component.component_type === 'markdown';

  /**
   * Execute JS code in a sandboxed iframe
   */
  const executeJs = useCallback((jsCode: string, htmlContent: string) => {
    if (!jsCode || !jsCode.trim() || !iframeRef.current) {
      return;
    }

    // Create the sandbox HTML with the component content and JS
    const sandboxHtml = `
      <!DOCTYPE html>
      <html>
      <head>
        <style>
          body { margin: 0; padding: 0; font-family: inherit; }
          * { box-sizing: border-box; }
        </style>
      </head>
      <body>
        <div id="component-root">${htmlContent}</div>
        <script>
          try {
            const root = document.getElementById('component-root');
            (function(root) {
              ${jsCode}
            })(root);
            parent.postMessage({ type: 'component-js-success', componentId: ${component.id} }, '*');
          } catch (error) {
            parent.postMessage({ 
              type: 'component-js-error', 
              componentId: ${component.id},
              message: error.message 
            }, '*');
          }
        ${'<'}/script>
      </body>
      </html>
    `;

    iframeRef.current.srcdoc = sandboxHtml;
  }, [component.id]);

  // Apply scoped CSS and execute JS when component mounts or updates
  useEffect(() => {
    if (!isHtmlLike) return;
    if (!containerRef.current) return;

    // If there's JS code, execute it in sandbox
    if (component.js_code && component.js_code.trim()) {
      executeJs(component.js_code, component.html_content);
    }
  }, [component.html_content, component.js_code, executeJs, isHtmlLike]);

  // Handle messages from the sandboxed iframe
  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'component-js-error' && event.data.componentId === component.id) {
        console.error(`Component ${component.id} JS Error:`, event.data.message);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [component.id]);

  // Generate scoped CSS
  const scopedCss = isHtmlLike && component.css_code
    ? component.css_code
        .split('}')
        .map((rule) => {
          if (rule.trim()) {
            return rule.replace(/([^{]+)({?)/, (match, selector, brace) => {
              const trimmedSelector = selector.trim();
              if (trimmedSelector && !trimmedSelector.startsWith('@')) {
                const scopedSelectors = trimmedSelector
                  .split(',')
                  .map((s: string) => `.component-${component.id} ${s.trim()}`)
                  .join(', ');
                return scopedSelectors + (brace || '');
              }
              return match;
            });
          }
          return rule;
        })
        .join('}')
    : '';

  if (component.component_type === 'google_sheet') {
    if (!component.google_sheet) {
      return null;
    }
    return (
      <div
        className={`page-component component-${component.id} ${className}`}
        data-component-type={component.component_type}
        data-component-name={component.name}
        data-component-order={component.order}
      >
        <GoogleSheetTable sheetId={component.google_sheet} tableStyle={component.google_sheet_style} />
      </div>
    );
  }

  // Only render HTML and Markdown component types (both use html_content)
  if (!isHtmlLike) {
    return null;
  }

  return (
    <>
      {/* Scoped CSS */}
      {scopedCss && <style>{scopedCss}</style>}
      
      {/* Component container */}
      <div
        ref={containerRef}
        className={`page-component component-${component.id} ${className}`}
        data-component-type={component.component_type}
        data-component-name={component.name}
        data-component-order={component.order}
      >
        {/* Main HTML content */}
        <div
          className="component-content"
          dangerouslySetInnerHTML={{ __html: component.html_content }}
        />
      </div>

      {/* Hidden sandbox iframe for JS execution */}
      {component.js_code && component.js_code.trim() && (
        <iframe
          ref={iframeRef}
          title={`component-sandbox-${component.id}`}
          sandbox="allow-scripts"
          style={{
            display: 'none',
            width: 0,
            height: 0,
            border: 'none',
          }}
        />
      )}
    </>
  );
};

interface ComponentListRendererProps {
  components: PageComponent[];
  className?: string;
}

/**
 * ComponentListRenderer renders a list of PageComponents in order.
 */
export const ComponentListRenderer = ({ components, className = '' }: ComponentListRendererProps) => {
  // Filter enabled components and sort by order
  const sortedComponents = [...components]
    .filter((c) => c.is_enabled)
    .sort((a, b) => a.order - b.order);

  return (
    <div className={`components-container ${className}`}>
      {sortedComponents.map((component) => (
        <ComponentRenderer key={component.id} component={component} />
      ))}
    </div>
  );
};
