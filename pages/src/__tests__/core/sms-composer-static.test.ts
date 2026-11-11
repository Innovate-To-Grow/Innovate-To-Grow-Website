// mail/js/sms-composer.js: the Broadcast SMS composer's live count. It must count as the server does
// (apps/core/services/delivery_rates/rules/sms_parts.py) and compose as the sender does (services/sms/compose.py).
import {afterEach, beforeAll, describe, expect, it} from 'vitest';

import {readRepoFile} from '@/__tests__/core/adminStatic';

const SCRIPT = 'src/apps/mail/static/mail/js/sms-composer.js';

interface Measured {
  encoding: string;
  characters: number;
  segments: number;
  offenders: string[];
}

interface Composer {
  measure: (text: string) => Measured;
  compose: (message: string, settings: Record<string, unknown>) => string;
  describe: (message: string, settings: Record<string, unknown>) => {lines: string[]; warn: boolean};
}

const SETTINGS = {
  footer: 'Reply STOP to opt out.',
  linkLength: 48,
  linkPlaceholders: ['login_link', 'ticket_link', 'event_link'],
  linksEnabled: false,
  names: {first_name: 'Hongzhe', last_name: 'Xie', full_name: 'Hongzhe Xie'},
  costPerSegment: '0.0100',
};

const composer = () => (window as unknown as {I2GSmsComposer: Composer}).I2GSmsComposer;

describe('sms-composer.js', () => {
  beforeAll(() => {
    window.eval(readRepoFile(SCRIPT));
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('counts GSM-7 like the server: 160 in one text, 153 per part, extension characters as two', () => {
    const {measure} = composer();
    expect(measure('a'.repeat(160))).toMatchObject({encoding: 'GSM-7', segments: 1});
    expect(measure('a'.repeat(161))).toMatchObject({encoding: 'GSM-7', segments: 2});
    expect(measure('a'.repeat(306))).toMatchObject({segments: 2});
    expect(measure('a'.repeat(307))).toMatchObject({segments: 3});
    expect(measure('€'.repeat(80))).toMatchObject({encoding: 'GSM-7', characters: 80, segments: 1});
    expect(measure('€'.repeat(81))).toMatchObject({segments: 2});
    expect(measure('')).toMatchObject({segments: 1, characters: 0});
  });

  it('counts UCS-2 when one character is outside GSM-7, and names it', () => {
    const {measure} = composer();
    expect(measure('é'.repeat(161))).toMatchObject({encoding: 'GSM-7'});
    expect(measure(`${'a'.repeat(69)}’`)).toMatchObject({encoding: 'UCS-2', segments: 1, offenders: ['’']});
    expect(measure(`${'a'.repeat(70)}’`)).toMatchObject({segments: 2});
    // An emoji is a surrogate pair: two code units, never split across parts.
    expect(measure('🎉'.repeat(35))).toMatchObject({encoding: 'UCS-2', characters: 35, segments: 1});
    expect(measure('🎉'.repeat(36))).toMatchObject({segments: 2});
  });

  it('composes as the sender does: names, full-length links, CR LF and the footer unless it says STOP', () => {
    const {compose} = composer();
    expect(compose('Hi {{ first_name }}\nsee {{event_link}}', SETTINGS)).toBe(
      `Hi Hongzhe\r\nsee ${'x'.repeat(48)}\nReply STOP to opt out.`,
    );
    expect(compose('Text STOP to quit', SETTINGS)).toBe('Text STOP to quit');
    expect(compose('Hi  ', {...SETTINGS, footer: ''})).toBe('Hi  ');
  });

  it('says what the text costs, and warns about UCS-2 and links that are off', () => {
    const {describe: describeText} = composer();
    const plain = describeText('Hello', SETTINGS);
    expect(plain.lines).toEqual(['GSM-7 · 28 characters · 1 segment · ≈ $0.0100 per recipient']);
    expect(plain.warn).toBe(false);
    const fancy = describeText('Party 🎉 {{login_link}}', SETTINGS);
    expect(fancy.lines[0]).toMatch(/^UCS-2 · /);
    expect(fancy.lines).toContain('These characters make every segment hold only 70 (67 when split): 🎉');
    expect(fancy.lines.at(-1)).toMatch(/Links in SMS are turned off/);
    expect(fancy.warn).toBe(true);
  });

  it('mounts under the message field and follows typing', () => {
    document.body.innerHTML = `
      <script type="application/json" id="sms-composer-settings">${JSON.stringify(SETTINGS)}</script>
      <div><textarea id="id_message">Hello</textarea></div>
      <div id="sms-composer-counter" class="hidden"></div>`;
    window.eval(readRepoFile(SCRIPT));

    const field = document.getElementById('id_message') as HTMLTextAreaElement;
    const counter = document.getElementById('sms-composer-counter') as HTMLElement;
    expect(field.nextElementSibling).toBe(counter);
    expect(counter.textContent).toContain('1 segment');
    field.value = 'a'.repeat(200);
    field.dispatchEvent(new Event('input'));
    expect(counter.textContent).toContain('2 segments');
    expect(counter.className).toContain('text-base-500');
  });

  it('does nothing on a page without the composer', () => {
    expect(() => window.eval(readRepoFile(SCRIPT))).not.toThrow();
  });
});
