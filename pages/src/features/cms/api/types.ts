import type {ContactInfoData} from '@/features/cms/components/blocks/content/ContactInfoBlock';
import type {CtaGroupData} from '@/features/cms/components/blocks/content/CtaGroupBlock';
import type {EmbedData} from '@/features/cms/components/blocks/content/EmbedBlock';
import type {EmbedWidgetData} from '@/features/cms/components/blocks/content/EmbedWidgetBlock';
import type {FaqListData} from '@/features/cms/components/blocks/content/FaqListBlock';
import type {HeroData} from '@/features/cms/components/blocks/content/HeroBlock';
import type {ImageTextData} from '@/features/cms/components/blocks/content/ImageTextBlock';
import type {LinkListData} from '@/features/cms/components/blocks/content/LinkListBlock';
import type {NoticeData} from '@/features/cms/components/blocks/content/NoticeBlock';
import type {NumberedListData} from '@/features/cms/components/blocks/content/NumberedListBlock';
import type {RichTextData} from '@/features/cms/components/blocks/content/RichTextBlock';
import type {TableBlockData} from '@/features/cms/components/blocks/content/TableBlock';
import type {NavigationGridData} from '@/features/cms/components/blocks/navigation/NavigationGridBlock';
import type {SectionGroupData} from '@/features/cms/components/blocks/navigation/SectionGroupBlock';
import type {ProposalCardsData} from '@/features/cms/components/blocks/showcase/ProposalCardsBlock';
import type {SponsorYearBlockData} from '@/features/cms/components/blocks/showcase/SponsorYearBlock';

interface CMSBlockBase {
  block_type: string;
  sort_order: number;
  data: Record<string, unknown>;
}

export type CMSKnownBlock =
  | {block_type: 'hero'; sort_order: number; data: HeroData}
  | {block_type: 'rich_text'; sort_order: number; data: RichTextData}
  | {block_type: 'contact_info'; sort_order: number; data: ContactInfoData}
  | {block_type: 'navigation_grid'; sort_order: number; data: NavigationGridData}
  | {block_type: 'link_list'; sort_order: number; data: LinkListData}
  | {block_type: 'cta_group'; sort_order: number; data: CtaGroupData}
  | {block_type: 'faq_list'; sort_order: number; data: FaqListData}
  | {block_type: 'image_text'; sort_order: number; data: ImageTextData}
  | {block_type: 'notice'; sort_order: number; data: NoticeData}
  | {block_type: 'section_group'; sort_order: number; data: SectionGroupData}
  | {block_type: 'proposal_cards'; sort_order: number; data: ProposalCardsData}
  | {block_type: 'table'; sort_order: number; data: TableBlockData}
  | {block_type: 'numbered_list'; sort_order: number; data: NumberedListData}
  | {block_type: 'sponsor_year'; sort_order: number; data: SponsorYearBlockData}
  | {block_type: 'embed'; sort_order: number; data: EmbedData}
  | {block_type: 'embed_widget'; sort_order: number; data: EmbedWidgetData};

export interface CMSUnknownBlock extends CMSBlockBase {
  block_type: string;
}

export type CMSBlock = CMSKnownBlock | CMSUnknownBlock;

export interface CMSPageResponse {
  slug: string;
  route: string;
  title: string;
  page_css_class: string;
  meta_description: string;
  blocks: CMSBlock[];
  expires_at?: string;
}

export interface CMSPageRedirectResponse {
  redirect_to: string;
  permanent: true;
}

export type CMSEmbedWidgetType = 'blocks' | 'app_route';

export interface CMSEmbedResponse {
  widget_type?: CMSEmbedWidgetType;
  app_route?: string;
  blocks: CMSBlock[];
  page_css_class: string;
  hidden_sections?: string[];
  hide_section_titles?: boolean;
  schedule_id?: string | null;
}
