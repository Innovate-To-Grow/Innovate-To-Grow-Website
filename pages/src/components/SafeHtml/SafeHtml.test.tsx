import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';

import {SafeHtml} from './SafeHtml';

describe('SafeHtml', () => {
  it('removes unsafe script and handler markup', () => {
    render(
      <SafeHtml html={'<p onclick="alert(1)">Hello</p><script>alert(1)</script>'} />,
    );

    const paragraph = screen.getByText('Hello');
    expect(paragraph).toBeInTheDocument();
    expect(paragraph).not.toHaveAttribute('onclick');
    expect(document.querySelector('script')).toBeNull();
  });
});
