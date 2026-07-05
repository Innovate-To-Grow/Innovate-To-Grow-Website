import { memo, type ReactNode } from 'react';
import type { CMSBlock, CMSKnownBlock, CMSKnownBlockType } from '@/features/cms/api';
import { ContactInfoBlock } from './blocks/content/ContactInfoBlock';
import { EmbedBlock } from './blocks/content/EmbedBlock';
import { EmbedWidgetBlock } from './blocks/content/EmbedWidgetBlock';
import { FaqListBlock } from './blocks/content/FaqListBlock';
import { ImageTextBlock } from './blocks/content/ImageTextBlock';
import { LinkListBlock } from './blocks/content/LinkListBlock';
import { RichTextBlock } from './blocks/content/RichTextBlock';
import { TableBlock } from './blocks/content/TableBlock';
import { NavigationGridBlock } from './blocks/navigation/NavigationGridBlock';
import { SectionGroupBlock } from './blocks/navigation/SectionGroupBlock';
import { ProposalCardsBlock } from './blocks/showcase/ProposalCardsBlock';
import { SponsorYearBlock } from './blocks/showcase/SponsorYearBlock';

type BlockComponentMap = {
  [Type in CMSKnownBlockType]: (props: {
    data: Extract<CMSKnownBlock, {block_type: Type}>['data'];
    previewMode?: boolean;
  }) => ReactNode;
};

const BLOCK_COMPONENTS = {
  rich_text: RichTextBlock,
  contact_info: ContactInfoBlock,
  navigation_grid: NavigationGridBlock,
  link_list: LinkListBlock,
  faq_list: FaqListBlock,
  image_text: ImageTextBlock,
  section_group: SectionGroupBlock,
  proposal_cards: ProposalCardsBlock,
  table: TableBlock,
  sponsor_year: SponsorYearBlock,
  embed: EmbedBlock,
  embed_widget: EmbedWidgetBlock,
} satisfies BlockComponentMap;

function isKnownBlock(block: CMSBlock): block is CMSKnownBlock {
  return block.block_type in BLOCK_COMPONENTS;
}

function isPresentBlock(block: CMSBlock | null | undefined): block is CMSBlock {
  return Boolean(block);
}

function renderKnownBlock(block: CMSKnownBlock, previewMode: boolean) {
  const key = `${block.block_type}-${block.sort_order}`;

  switch (block.block_type) {
    case 'rich_text': {
      const Component = BLOCK_COMPONENTS.rich_text;
      return <Component key={key} data={block.data} />;
    }
    case 'contact_info': {
      const Component = BLOCK_COMPONENTS.contact_info;
      return <Component key={key} data={block.data} />;
    }
    case 'navigation_grid': {
      const Component = BLOCK_COMPONENTS.navigation_grid;
      return <Component key={key} data={block.data} />;
    }
    case 'link_list': {
      const Component = BLOCK_COMPONENTS.link_list;
      return <Component key={key} data={block.data} />;
    }
    case 'faq_list': {
      const Component = BLOCK_COMPONENTS.faq_list;
      return <Component key={key} data={block.data} />;
    }
    case 'image_text': {
      const Component = BLOCK_COMPONENTS.image_text;
      return <Component key={key} data={block.data} />;
    }
    case 'section_group': {
      const Component = BLOCK_COMPONENTS.section_group;
      return <Component key={key} data={block.data} />;
    }
    case 'proposal_cards': {
      const Component = BLOCK_COMPONENTS.proposal_cards;
      return <Component key={key} data={block.data} />;
    }
    case 'table': {
      const Component = BLOCK_COMPONENTS.table;
      return <Component key={key} data={block.data} />;
    }
    case 'sponsor_year': {
      const Component = BLOCK_COMPONENTS.sponsor_year;
      return <Component key={key} data={block.data} />;
    }
    case 'embed': {
      const Component = BLOCK_COMPONENTS.embed;
      return <Component key={key} data={block.data} previewMode={previewMode} />;
    }
    case 'embed_widget': {
      const Component = BLOCK_COMPONENTS.embed_widget;
      return <Component key={key} data={block.data} previewMode={previewMode} />;
    }
    default: {
      const exhaustive: never = block;
      return exhaustive;
    }
  }
}

export const BlockRenderer = memo(
  ({ blocks, previewMode = false }: { blocks: Array<CMSBlock | null | undefined>; previewMode?: boolean }) => (
    <>
      {blocks.filter(isPresentBlock).map((block) => {
        if (!isKnownBlock(block)) {
          console.warn(`Unknown CMS block type: ${block.block_type}`);
          return null;
        }
        return renderKnownBlock(block, previewMode);
      })}
    </>
  ),
);
