import {describe, expect, it} from 'vitest';

import {hasRequiredNameFields} from './profileCompletion';

describe('hasRequiredNameFields', () => {
  it('returns true when both names are present', () => {
    expect(hasRequiredNameFields({first_name: 'Alice', last_name: 'Smith'})).toBe(true);
  });

  it('returns false when first_name is missing', () => {
    expect(hasRequiredNameFields({first_name: '', last_name: 'Smith'})).toBe(false);
  });

  it('returns false when last_name is missing', () => {
    expect(hasRequiredNameFields({first_name: 'Alice', last_name: ''})).toBe(false);
  });

  it('returns false when both are missing', () => {
    expect(hasRequiredNameFields({first_name: '', last_name: ''})).toBe(false);
  });

  it('returns false for null input', () => {
    expect(hasRequiredNameFields(null)).toBe(false);
  });

  it('returns false for undefined input', () => {
    expect(hasRequiredNameFields(undefined)).toBe(false);
  });

  it('returns false for whitespace-only names', () => {
    expect(hasRequiredNameFields({first_name: '   ', last_name: '  '})).toBe(false);
  });

  it('returns false when first_name is null', () => {
    expect(hasRequiredNameFields({first_name: null, last_name: 'Smith'})).toBe(false);
  });

  it('returns false when last_name is null', () => {
    expect(hasRequiredNameFields({first_name: 'Alice', last_name: null})).toBe(false);
  });
});
