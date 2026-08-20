import {render} from '@testing-library/react';
import {describe, expect, it} from 'vitest';

import {Icon} from '@/components/Icon/Icon';

const CMS_SOCIAL_ICONS = [
  'fa fa-facebook',
  'fa fa-twitter',
  'fa fa-linkedin',
  'fa fa-instagram',
  'fa fa-youtube',
  'fa fa-github',
] as const;

describe('Icon social brands', () => {
  it.each(CMS_SOCIAL_ICONS)('renders %s as a filled brand glyph', (name) => {
    const {container} = render(<Icon name={name} />);
    const icon = container.querySelector('svg');
    const path = container.querySelector('path');

    expect(icon).toHaveAttribute('fill', 'currentColor');
    expect(icon).toHaveAttribute('stroke', 'none');
    expect(path).toHaveAttribute('transform', 'translate(0 1536) scale(1 -1)');
  });

  it('uses a distinct glyph for every social platform supported by the CMS', () => {
    const paths = CMS_SOCIAL_ICONS.map((name) => {
      const {container} = render(<Icon name={name} />);
      return container.querySelector('path')?.getAttribute('d');
    });

    expect(new Set(paths).size).toBe(CMS_SOCIAL_ICONS.length);
  });
});
