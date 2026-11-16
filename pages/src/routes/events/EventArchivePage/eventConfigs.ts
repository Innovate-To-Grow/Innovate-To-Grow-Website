import {configsFrom2025To2024} from './from2025To2024';
import {configsFrom2023To2022} from './from2023To2022';
import {configsFrom2021To2020} from './from2021To2020';
import type {EventConfig} from './types';

export type {EventConfig} from './types';

/**
 * Presentation-only schedule layout for archived events.
 * Spreadsheet sourcing now lives in the backend.
 */
export const EVENT_CONFIGS: Record<string, EventConfig> = {
  ...configsFrom2025To2024,
  ...configsFrom2023To2022,
  ...configsFrom2021To2020,
};
