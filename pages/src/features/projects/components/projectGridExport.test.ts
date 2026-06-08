import {describe, expect, it} from 'vitest';

import {createPdfProjectTableBody, createProjectRowsCsvText, createProjectRowsWordBlob} from './projectGridExport';
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
  it('adds project detail rows to PDF project tables', () => {
    const body = createPdfProjectTableBody([row]);
    const detailCell = (body[1] as Array<{colSpan: number; content: string}>)[0];

    expect(body[0]).toContain('Rotary Joint Testing System');
    expect(detailCell).toMatchObject({
      colSpan: 7,
      content: expect.stringContaining('Project Detail\nAbstract: A detailed abstract with <special> characters & project context.'),
    });
    expect(detailCell).toMatchObject({
      content: expect.stringContaining('Student Names: Alice Calderon, Bob Lee'),
    });
  });

  it('includes edited project detail text before CSV project rows', () => {
    const csv = createProjectRowsCsvText([row], {
      detailsText: '<strong>Edited Past Projects Detail</strong><br><mark>Highlighted project detail & owner edits</mark>',
      title: 'Saved Merged Results',
    });

    expect(csv).toContain('Innovate to Grow Past Projects\r\nI2G Logo,/assets/images/i2glogo.png');
    expect(csv).toContain('Title,Saved Merged Results');
    expect(csv).toContain('Past Projects Detail\r\nEdited Past Projects Detail\r\nHighlighted project detail & owner edits');
    expect(csv).toContain('\r\nProjects\r\nYear-Semester,Class,Team#,Team Name,Project Title');
    expect(csv).toContain('A detailed abstract with <special> characters & project context.');
  });

  it('neutralizes leading formula characters in CSV cells to prevent CSV injection', () => {
    const csv = createProjectRowsCsvText(
      [
        {
          ...row,
          project_title: '=HYPERLINK("http://evil","click")',
          organization: '+1-800-EVIL',
          student_names: '@SUM(A1:A9)',
          team_name: '-2+3',
        },
      ],
      {
        title: '=cmd|\'/c calc\'!A1',
        detailsText: '=1+1 danger',
      },
    );

    // Title and detail lines starting with = are prefixed with a quote, then CSV-quoted
    // because they also contain a comma / quote where applicable.
    expect(csv).toContain("'=cmd");
    expect(csv).toContain("'=1+1 danger");
    // Project columns are neutralized too (quoted because they contain commas/quotes).
    expect(csv).toContain('"\'=HYPERLINK(""http://evil"",""click"")"');
    expect(csv).toContain("'+1-800-EVIL");
    expect(csv).toContain("'@SUM(A1:A9)");
    expect(csv).toContain("'-2+3");
    // No raw formula cell survives at the start of a field.
    expect(csv).not.toMatch(/(^|,)=HYPERLINK/m);
    expect(csv).not.toMatch(/(^|,)@SUM/m);
  });

  it('falls back to generated detail text for CSV exports when no edited detail text is provided', () => {
    const csv = createProjectRowsCsvText([row]);

    expect(csv).toContain('Past Projects Detail');
    expect(csv).toContain('Project 1');
    expect(csv).toContain('Students: Alice Calderon, Bob Lee');
    expect(csv).toContain('Abstract: A detailed abstract with <special> characters & project context.');
  });

  it('creates a real docx package for Word exports', async () => {
    const blob = createProjectRowsWordBlob(
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
    const blob = createProjectRowsWordBlob([row], {
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
