import { memo } from 'react';
import type { CMSBlock } from '../../features/cms/api';
import { ContactInfoBlock } from './blocks/content/ContactInfoBlock';
import { FaqListBlock } from './blocks/content/FaqListBlock';
import { ImageTextBlock } from './blocks/content/ImageTextBlock';
import { LinkListBlock } from './blocks/content/LinkListBlock';
import { RichTextBlock } from './blocks/content/RichTextBlock';
import { TableBlock } from './blocks/content/TableBlock';
import { NavigationGridBlock } from './blocks/navigation/NavigationGridBlock';
import { SectionGroupBlock } from './blocks/navigation/SectionGroupBlock';
import { ProposalCardsBlock } from './blocks/showcase/ProposalCardsBlock';
import { SponsorYearBlock } from './blocks/showcase/SponsorYearBlock';

/* eslint-disable @typescript-eslint/no-explicit-any */
type BlockComponent = React.FC<{ data: any }>;

const BLOCK_COMPONENTS: Record<string, BlockComponent> = {
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
};

interface BlockRendererProps {
  blocks: CMSBlock[];
}

export const BlockRenderer: React.FC<BlockRendererProps> = memo(({ blocks }) => (
  <>
    {blocks.map((block) => {
      const Component = BLOCK_COMPONENTS[block.block_type];
      if (!Component) {
        console.warn(`Unknown CMS block type: ${block.block_type}`);
        return null;
      }
      return <Component key={`${block.block_type}-${block.sort_order}`} data={block.data} />;
    })}
  </>
));
