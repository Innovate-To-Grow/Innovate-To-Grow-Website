import type {ComponentProps} from 'react';

import ReactMarkdown, {type Components} from 'react-markdown';
import remarkGfm from 'remark-gfm';

import {isSafeHref} from './markdownLinks';

const components: Components = {
  // Anchors: render external links safely, neutralize everything else to text.
  a({href, children, ...rest}) {
    if (!isSafeHref(href)) {
      return <span>{children}</span>;
    }
    // Spread first: the security attributes must win over anything in rest.
    return (
      <a {...rest} href={href} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
};

/**
 * Single source of truth for URL safety: react-markdown's default transform
 * would strip `tel:` (not in its allowlist), so route every URL through the
 * same whitelist the anchor renderer uses. Unsafe URLs become '' and the
 * anchor renderer then degrades them to plain text.
 */
const transformUrl = (url: string): string => (isSafeHref(url) ? url : '');

/**
 * Inner markdown renderer. Statically imports `react-markdown` + `remark-gfm`
 * so they land in this lazily-loaded chunk instead of the main bundle — never
 * import this module from anything reachable by the entrypoint.
 *
 * Raw HTML stays escaped (no `rehype-raw`), so the output is XSS-safe by
 * construction.
 */
export default function MarkdownMessageImpl({content}: {content: string}) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      urlTransform={transformUrl}
      components={components}
    >
      {content}
    </ReactMarkdown>
  );
}

export type MarkdownMessageImplProps = ComponentProps<typeof MarkdownMessageImpl>;
