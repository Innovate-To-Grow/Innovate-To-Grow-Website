import type { CMSBlock } from '../../services/api/cms';
import { ContactInfoBlock } from './blocks/ContactInfoBlock';
import { FaqListBlock } from './blocks/FaqListBlock';
import { ImageTextBlock } from './blocks/ImageTextBlock';
import { LinkListBlock } from './blocks/LinkListBlock';
import { NavigationGridBlock } from './blocks/NavigationGridBlock';
import { ProposalCardsBlock } from './blocks/ProposalCardsBlock';
import { RichTextBlock } from './blocks/RichTextBlock';
import { SectionGroupBlock } from './blocks/SectionGroupBlock';

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
};

interface BlockRendererProps {
  blocks: CMSBlock[];
}

export const BlockRenderer: React.FC<BlockRendererProps> = ({ blocks }) => (
  <>
    {blocks.map((block, i) => {
      const Component = BLOCK_COMPONENTS[block.block_type];
      if (!Component) {
        console.warn(`Unknown CMS block type: ${block.block_type}`);
        return null;
      }
      return <Component key={i} data={block.data} />;
    })}
  </>
);
