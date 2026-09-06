import {cleanup, render} from '@testing-library/react';
import {afterEach, describe, expect, it} from 'vitest';

import {TableBlock} from '@/features/cms/components/blocks/content/TableBlock';

describe('TableBlock', () => {
  afterEach(() => {
    cleanup();
  });

  it('renders the wrapper and a heading only when provided', () => {
    const {container} = render(
      <TableBlock data={{heading: 'Results', columns: [], rows: []}} />,
    );
    expect(container.querySelector('.cms-table-block')).not.toBeNull();
    expect(container.querySelector('h2.cms-table-block-title')?.textContent).toBe('Results');

    const {container: noHeading} = render(<TableBlock data={{columns: [], rows: []}} />);
    expect(noHeading.querySelector('h2.cms-table-block-title')).toBeNull();
  });

  it('renders columns as header cells', () => {
    const {container} = render(
      <TableBlock data={{columns: ['Name', 'Score'], rows: []}} />,
    );
    const headers = container.querySelectorAll('th');
    expect(headers).toHaveLength(2);
    expect(headers[0].textContent).toBe('Name');
    expect(headers[1].textContent).toBe('Score');
  });

  it('omits the thead when columns are absent', () => {
    const {container} = render(<TableBlock data={{rows: [['a', 'b']]}} />);
    expect(container.querySelector('thead')).toBeNull();
  });

  it('renders array rows as cells, blanking null/undefined', () => {
    const {container} = render(
      <TableBlock data={{columns: ['A', 'B'], rows: [['x', null], [undefined, 5]]}} />,
    );
    const rows = container.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(2);
    const cells = container.querySelectorAll('tbody td');
    expect(cells).toHaveLength(4);
    expect(cells[0].textContent).toBe('x');
    expect(cells[1].textContent).toBe('');
    expect(cells[2].textContent).toBe('');
    expect(cells[3].textContent).toBe('5');
  });

  it('renders object rows keyed by the column list', () => {
    const {container} = render(
      <TableBlock
        data={{columns: ['name', 'age'], rows: [{name: 'Ada', age: 36, extra: 'x'}]}}
      />,
    );
    const cells = container.querySelectorAll('tbody td');
    expect(cells).toHaveLength(2);
    expect(cells[0].textContent).toBe('Ada');
    expect(cells[1].textContent).toBe('36');
  });

  it('renders object rows by their own values when columns are empty', () => {
    const {container} = render(
      <TableBlock data={{columns: [], rows: [{name: 'Ada', age: 36}]}} />,
    );
    expect(container.querySelector('thead')).toBeNull();
    const cells = container.querySelectorAll('tbody td');
    expect(cells).toHaveLength(2);
    expect(cells[0].textContent).toBe('Ada');
    expect(cells[1].textContent).toBe('36');
  });

  it('renders primitive rows as a single cell', () => {
    const {container} = render(
      <TableBlock data={{columns: [], rows: ['only', 7, true]}} />,
    );
    const rows = container.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(3);
    const cells = container.querySelectorAll('tbody td');
    expect(cells).toHaveLength(3);
    expect(cells[0].textContent).toBe('only');
    expect(cells[1].textContent).toBe('7');
    expect(cells[2].textContent).toBe('true');
  });

  it('stringifies object cells via JSON', () => {
    const {container} = render(
      <TableBlock data={{columns: [], rows: [[{a: 1}]]}} />,
    );
    expect(container.querySelector('tbody td')?.textContent).toBe('{"a":1}');
  });

  it('falls back to String() when a cell cannot be JSON-stringified', () => {
    const {container} = render(<TableBlock data={{columns: [], rows: [1n]}} />);
    expect(container.querySelector('tbody td')?.textContent).toBe('1');
  });

  it('stringifies non-string column values', () => {
    const {container} = render(<TableBlock data={{columns: ['Count', 42], rows: []}} />);
    const headers = container.querySelectorAll('th');
    expect(headers).toHaveLength(2);
    expect(headers[1].textContent).toBe('42');
  });

  it('renders an empty table when no rows are supplied', () => {
    const {container} = render(<TableBlock data={{}} />);
    expect(container.querySelector('thead')).toBeNull();
    expect(container.querySelectorAll('tbody tr')).toHaveLength(0);
  });
});
