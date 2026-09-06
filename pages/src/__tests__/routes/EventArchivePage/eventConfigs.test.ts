import {describe, expect, it} from 'vitest';

import {EVENT_CONFIGS} from '@/routes/EventArchivePage/eventConfigs';
import {configsFrom2021To2020} from '@/routes/EventArchivePage/configs/from2021To2020';
import {configsFrom2023To2022} from '@/routes/EventArchivePage/configs/from2023To2022';
import {configsFrom2025To2024} from '@/routes/EventArchivePage/configs/from2025To2024';

describe('EVENT_CONFIGS', () => {
  const sourceMaps = [
    configsFrom2025To2024,
    configsFrom2023To2022,
    configsFrom2021To2020,
  ];

  it('merges the three source config maps without collisions', () => {
    const expected = Object.assign({}, ...sourceMaps);
    expect(EVENT_CONFIGS).toEqual(expected);
  });

  it('exposes the expected eleven archive events', () => {
    expect(Object.keys(EVENT_CONFIGS)).toHaveLength(11);
    expect(Object.keys(EVENT_CONFIGS)).toEqual(
      expect.arrayContaining([
        '2025-fall',
        '2025-spring',
        '2024-fall',
        '2024-spring',
        '2023-fall',
        '2023-spring',
        '2022-fall',
        '2022-spring',
        '2021-fall',
        '2021-spring',
        '2020-fall',
      ]),
    );
  });

  it('keeps every class track label list aligned with its track count', () => {
    for (const [key, config] of Object.entries(EVENT_CONFIGS)) {
      expect(config.title, `${key} title`).toBeTruthy();
      expect(config.semester, `${key} semester`).toBeTruthy();
      expect(config.classes.length, `${key} classes`).toBeGreaterThan(0);
      for (const cls of config.classes) {
        expect(cls.code, `${key}/${cls.code} code`).toBeTruthy();
        expect(cls.label, `${key}/${cls.code} label`).toBeTruthy();
        expect(cls.trackLabels, `${key}/${cls.code} track labels`).toHaveLength(
          cls.trackCount,
        );
      }
    }
  });

  it('uses the shared class config shape for every source map', () => {
    for (const sourceMap of sourceMaps) {
      for (const config of Object.values(sourceMap)) {
        for (const cls of config.classes) {
          expect(typeof cls.startTime).toBe('string');
          expect(typeof cls.slotMinutes).toBe('number');
          expect(typeof cls.orderCount).toBe('number');
        }
      }
    }
  });
});
