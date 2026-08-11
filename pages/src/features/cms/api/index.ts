import { api } from '@/lib/api';
import type {ContactInfoData} from '@/features/cms/components/blocks/content/ContactInfoBlock';
import type {EmbedData} from '@/features/cms/components/blocks/content/EmbedBlock';
import type {EmbedWidgetData} from '@/features/cms/components/blocks/content/EmbedWidgetBlock';
import type {FaqListData} from '@/features/cms/components/blocks/content/FaqListBlock';
import type {ImageTextData} from '@/features/cms/components/blocks/content/ImageTextBlock';
import type {LinkListData} from '@/features/cms/components/blocks/content/LinkListBlock';
import type {RichTextData} from '@/features/cms/components/blocks/content/RichTextBlock';
import type {TableBlockData} from '@/features/cms/components/blocks/content/TableBlock';
import type {NavigationGridData} from '@/features/cms/components/blocks/navigation/NavigationGridBlock';
import type {SectionGroupData} from '@/features/cms/components/blocks/navigation/SectionGroupBlock';
import type {ProposalCardsData} from '@/features/cms/components/blocks/showcase/ProposalCardsBlock';
import type {SponsorYearBlockData} from '@/features/cms/components/blocks/showcase/SponsorYearBlock';

const URL_SCHEME_RE = /^[A-Za-z][A-Za-z0-9+.-]*:/;

function hasControlCharacter(value: string): boolean {
  return Array.from(value).some((character) => {
    const code = character.charCodeAt(0);
    return code <= 0x1f || code === 0x7f;
  });
}

interface CMSBlockBase {
  block_type: string;
  sort_order: number;
  data: Record<string, unknown>;
}

export type CMSKnownBlock =
  | {block_type: 'rich_text'; sort_order: number; data: RichTextData}
  | {block_type: 'contact_info'; sort_order: number; data: ContactInfoData}
  | {block_type: 'navigation_grid'; sort_order: number; data: NavigationGridData}
  | {block_type: 'link_list'; sort_order: number; data: LinkListData}
  | {block_type: 'faq_list'; sort_order: number; data: FaqListData}
  | {block_type: 'image_text'; sort_order: number; data: ImageTextData}
  | {block_type: 'section_group'; sort_order: number; data: SectionGroupData}
  | {block_type: 'proposal_cards'; sort_order: number; data: ProposalCardsData}
  | {block_type: 'table'; sort_order: number; data: TableBlockData}
  | {block_type: 'sponsor_year'; sort_order: number; data: SponsorYearBlockData}
  | {block_type: 'embed'; sort_order: number; data: EmbedData}
  | {block_type: 'embed_widget'; sort_order: number; data: EmbedWidgetData};

export type CMSKnownBlockType = CMSKnownBlock['block_type'];

export interface CMSUnknownBlock extends CMSBlockBase {
  block_type: string;
}

export type CMSBlock = CMSKnownBlock | CMSUnknownBlock;

export interface CMSPageResponse {
  slug: string;
  route: string;
  title: string;
  page_css_class: string;
  page_css: string;
  meta_description: string;
  blocks: CMSBlock[];
  expires_at?: string;
}

export interface CMSPageRedirectResponse {
  redirect_to: string;
  permanent: true;
}

export type CMSPageFetchResponse = CMSPageResponse | CMSPageRedirectResponse;

export function isCMSPageRedirectResponse(
  response: CMSPageFetchResponse,
): response is CMSPageRedirectResponse {
  return (
    'redirect_to' in response
    && typeof response.redirect_to === 'string'
    && response.permanent === true
  );
}

export function normalizeCMSRoute(route: string): string {
  const trimmed = route.trim();
  if (!trimmed || trimmed === '/') {
    return '/';
  }

  if (
    URL_SCHEME_RE.test(trimmed)
    || trimmed.startsWith('//')
    || trimmed.includes('\\')
    || trimmed.includes('?')
    || trimmed.includes('#')
    || hasControlCharacter(trimmed)
  ) {
    throw new Error('CMS route must be a safe site-relative pathname.');
  }

  const segments = trimmed.split('/').filter(Boolean).map((segment) => {
    let decoded: string;
    try {
      decoded = decodeURIComponent(segment);
    } catch {
      throw new Error('CMS route contains invalid percent encoding.');
    }

    if (
      decoded === '.'
      || decoded === '..'
      || decoded.includes('/')
      || decoded.includes('\\')
      || hasControlCharacter(decoded)
    ) {
      throw new Error('CMS route contains an unsafe path segment.');
    }
    return decoded;
  });

  return segments.length > 0 ? `/${segments.join('/')}` : '/';
}

export async function fetchCMSPage(
  route: string,
  preview = false,
): Promise<CMSPageFetchResponse> {
  const normalizedRoute = normalizeCMSRoute(route);
  const path = normalizedRoute
    .split('/')
    .filter(Boolean)
    .map((segment) => encodeURIComponent(segment))
    .join('/');
  const params = new URLSearchParams();
  if (preview) params.set('preview', 'true');
  const qs = params.toString();
  const url = `/cms/pages/${path}${path ? '/' : ''}${qs ? `?${qs}` : ''}`;
  const response = await api.get<CMSPageFetchResponse>(url);
  return response.data;
}

export async function fetchCMSPreview(
  token: string,
): Promise<CMSPageResponse> {
  const response = await api.get<CMSPageResponse>(
    `/cms/preview/${encodeURIComponent(token)}/`,
  );
  return response.data;
}

export async function fetchCMSLivePreview(
  pageId: string,
): Promise<CMSPageResponse> {
  const response = await api.get<CMSPageResponse>(
    `/cms/live-preview/${encodeURIComponent(pageId)}/`,
  );
  return response.data;
}

export type CMSEmbedWidgetType = 'blocks' | 'app_route';

export interface CMSEmbedResponse {
  widget_type?: CMSEmbedWidgetType;
  app_route?: string;
  blocks: CMSBlock[];
  page_css_class: string;
  page_css: string;
  hidden_sections?: string[];
  hide_section_titles?: boolean;
  schedule_id?: string | null;
}

export interface CMSEmbedHostsResponse {
  hosts: string[];
  revision: string;
}

export async function fetchCMSEmbedHosts(): Promise<CMSEmbedHostsResponse> {
  const response = await api.get<CMSEmbedHostsResponse>('/cms/embed-hosts/');
  return response.data;
}

export async function fetchCMSEmbed(
  embedSlug: string,
): Promise<CMSEmbedResponse> {
  const response = await api.get<CMSEmbedResponse>(`/cms/embed/${embedSlug}/`);
  return response.data;
}
