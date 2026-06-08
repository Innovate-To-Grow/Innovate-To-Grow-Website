import {describe, expect, it} from 'vitest';

import {createSharedProjectRowsWordBlob} from './projectGridExport';
import type {ProjectGridRow} from './projectGrid';

const row: ProjectGridRow = {
  semester_label: '2025 Spring',
  class_code: 'CAP',
  team_number: '101',
  team_name: 'General Rotary and Professional Engineering',
  project_title: 'Rotary Joint Testing System',
  organization: 'E&J Gallo Winery',
  industry: 'Food Processing',
  abstract: 'A detailed abstract with <special> characters & project context.',
  student_names: 'Alice Calderon, Bob Lee',
  is_presenting: '',
};

const logo = {
  base64: 'iVBORw0KGgo=',
  bytes: Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]),
  dataUrl: 'data:image/png;base64,iVBORw0KGgo=',
  extension: 'png' as const,
};

describe('projectGridExport', () => {
  it('creates a real docx package for shared Word exports', async () => {
    const blob = createSharedProjectRowsWordBlob(
      [row],
      {
        title: 'Shared Results',
        note: 'Owner note & review instructions',
        detailsText: '<strong>Edited Past Projects Detail</strong><br><mark>Highlighted project detail & owner edits</mark>',
      },
      logo,
    );

    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.wordprocessingml.document');

    const bytes = new Uint8Array(await blob.arrayBuffer());
    expect(String.fromCharCode(...bytes.slice(0, 2))).toBe('PK');

    const packageText = new TextDecoder().decode(bytes);
    expect(packageText).toContain('[Content_Types].xml');
    expect(packageText).toContain('word/document.xml');
    expect(packageText).toContain('word/_rels/document.xml.rels');
    expect(packageText).toContain('word/media/i2g-logo.png');
    expect(packageText).toContain('rIdLogo');
    expect(packageText).toContain('Shared Results');
    expect(packageText).toContain('Owner note &amp; review instructions');
    expect(packageText).toContain('Past Projects Detail');
    expect(packageText).toContain('Edited Past Projects Detail');
    expect(packageText).toContain('Highlighted project detail &amp; owner edits');
    expect(packageText).toContain('A detailed abstract with &lt;special&gt; characters &amp; project context.');
  });

  it('falls back to generated detail text when a shared export has no saved detail text', async () => {
    const blob = createSharedProjectRowsWordBlob([row], {
      title: 'Shared Results',
      note: '',
    });

    const packageText = new TextDecoder().decode(new Uint8Array(await blob.arrayBuffer()));

    expect(packageText).toContain('Past Projects Detail');
    expect(packageText).toContain('Project 1');
    expect(packageText).toContain('Students: Alice Calderon, Bob Lee');
    expect(packageText).toContain('Abstract: A detailed abstract with &lt;special&gt; characters &amp; project context.');
  });
});
