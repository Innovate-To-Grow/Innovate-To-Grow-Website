import {describe, expect, it} from 'vitest';
import {safeHref} from './safeHref';

describe('safeHref', () => {
  it('blocks javascript: URLs', () => {
    expect(safeHref('javascript:alert(1)')).toBe('#');
    expect(safeHref('JAVASCRIPT:alert(1)')).toBe('#');
    expect(safeHref('JavaScript:void(0)')).toBe('#');
  });

  it('blocks data: URLs', () => {
    expect(safeHref('data:text/html,<script>alert(1)</script>')).toBe('#');
  });

  it('blocks vbscript: URLs', () => {
    expect(safeHref('vbscript:MsgBox("XSS")')).toBe('#');
  });

  it('allows http and https', () => {
    expect(safeHref('http://example.com')).toBe('http://example.com');
    expect(safeHref('https://example.com/path')).toBe('https://example.com/path');
  });

  it('allows mailto and tel', () => {
    expect(safeHref('mailto:test@example.com')).toBe('mailto:test@example.com');
    expect(safeHref('tel:+1234567890')).toBe('tel:+1234567890');
  });

  it('allows relative paths', () => {
    expect(safeHref('/about')).toBe('/about');
    expect(safeHref('./page')).toBe('./page');
    expect(safeHref('../parent')).toBe('../parent');
  });

  it('allows fragment URLs', () => {
    expect(safeHref('#section')).toBe('#section');
  });

  it('returns # for empty or non-string input', () => {
    expect(safeHref('')).toBe('#');
    expect(safeHref(null)).toBe('#');
    expect(safeHref(undefined)).toBe('#');
    expect(safeHref(123 as unknown as string)).toBe('#');
  });

  it('trims whitespace before validation', () => {
    expect(safeHref('  https://example.com  ')).toBe('https://example.com');
    expect(safeHref('  javascript:alert(1)  ')).toBe('#');
  });
});
