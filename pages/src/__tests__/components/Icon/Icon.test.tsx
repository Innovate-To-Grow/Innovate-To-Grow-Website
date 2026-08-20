import {render} from '@testing-library/react';
import {describe, expect, it} from 'vitest';

import {Icon} from '@/components/Icon/Icon';

describe('Icon', () => {
  it('uses font-relative dimensions and the legacy styling hook by default', () => {
    const {container} = render(<Icon name="sign-out" />);
    const icon = container.querySelector('svg');

    expect(icon).toHaveAttribute('width', '1em');
    expect(icon).toHaveAttribute('height', '1em');
    expect(icon).toHaveClass('fa');
  });

  it('keeps caller classes and explicit dimensions', () => {
    const {container} = render(
      <Icon name="cog" className="member-icon" width={20} height={18} />,
    );
    const icon = container.querySelector('svg');

    expect(icon).toHaveClass('fa', 'member-icon');
    expect(icon).toHaveAttribute('width', '20');
    expect(icon).toHaveAttribute('height', '18');
  });
});
