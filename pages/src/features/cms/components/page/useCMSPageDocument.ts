import {useEffect, useRef, useState} from 'react';
import {usePageTitle} from '@/hooks/usePageTitle';
import type {CMSPageResponse} from '../../api';

/**
 * The document-level effects of showing a CMS page: its title (tab and og:title), the editor's meta
 * description, and a visually hidden h1 fallback for pages whose blocks render none (an embedded archive
 * page, a home page of cards) — screen readers and search engines still need one. Returns the content ref
 * to attach and whether the h1 is needed.
 */
export function useCMSPageDocument(page: CMSPageResponse | null, isLivePreview: boolean) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [needsFallbackTitle, setNeedsFallbackTitle] = useState(false);

  const suffix = isLivePreview ? ' [Live Preview]' : '';
  usePageTitle(page?.title ? `${page.title}${suffix}` : null, {description: page?.meta_description});

  // Blocks can render (and lazy-load) after this effect, so keep checking as the content changes.
  useEffect(() => {
    const root = contentRef.current;
    if (!root || !page) return;
    const check = () => setNeedsFallbackTitle(!root.querySelector('h1'));
    check();
    const observer = new MutationObserver(check);
    observer.observe(root, {childList: true, subtree: true});
    return () => observer.disconnect();
  }, [page]);

  return {contentRef, needsFallbackTitle};
}
