import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';

import {SafeHtml} from '@/components/SafeHtml/SafeHtml';

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

  it('re-sanitizes unsafe links when CMS HTML changes', () => {
    const {rerender} = render(<SafeHtml html={'<a href="https://example.org">Project</a>'} />);
    expect(screen.getByRole('link', {name: 'Project'})).toHaveAttribute('href', 'https://example.org');

    rerender(
      <SafeHtml
        html={'<a href="javascript:alert(1)" onclick="alert(1)">Project</a><a href="https://example.org/safe">Safe</a>'}
      />,
    );

    const unsafeLink = screen.getByText('Project');
    expect(unsafeLink).not.toHaveAttribute('href');
    expect(unsafeLink).not.toHaveAttribute('onclick');
    expect(screen.getByRole('link', {name: 'Safe'})).toHaveAttribute('href', 'https://example.org/safe');
  });
});
