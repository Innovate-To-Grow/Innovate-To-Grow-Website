import {render, screen} from '@testing-library/react';
import {describe, expect, it} from 'vitest';

import {TableBlock} from '@/features/cms/components/blocks/content/TableBlock';

describe('TableBlock', () => {
  it('renders heading, columns, object rows, array rows, and primitive rows', () => {
    const circular: Record<string, unknown> = {};
    circular.self = circular;

    render(
      <TableBlock
        data={{
          heading: 'Project stats',
          columns: ['Name', 'Count', 'Meta'],
          rows: [
            {Name: 'Robots', Count: 3, Meta: {featured: true}},
            ['Sensors', false, null],
            'Standalone',
            {Name: 'Circular', Count: 1, Meta: circular},
          ],
        }}
      />,
    );

    expect(screen.getByRole('heading', {name: 'Project stats'})).toBeInTheDocument();
    expect(screen.getByRole('columnheader', {name: 'Name'})).toBeInTheDocument();
    expect(screen.getByText('Robots')).toBeInTheDocument();
    expect(screen.getByText('{"featured":true}')).toBeInTheDocument();
    expect(screen.getByText('false')).toBeInTheDocument();
    expect(screen.getByText('Standalone')).toBeInTheDocument();
    expect(screen.getByText('[object Object]')).toBeInTheDocument();
  });

  it('uses object values when columns are omitted', () => {
    render(<TableBlock data={{rows: [{name: 'Ada', role: 'Engineer'}]}} />);

    expect(screen.getByText('Ada')).toBeInTheDocument();
    expect(screen.getByText('Engineer')).toBeInTheDocument();
    expect(screen.queryByRole('columnheader')).not.toBeInTheDocument();
  });
});
