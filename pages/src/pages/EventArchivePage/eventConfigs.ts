import {configsFrom2025To2024} from './configs/from2025To2024';
import {configsFrom2023To2022} from './configs/from2023To2022';
import {configsFrom2021To2020} from './configs/from2021To2020';
import type {EventConfig} from './configs/types';

export type {EventConfig} from './configs/types';

/**
 * Presentation-only schedule layout for archived events.
 * Spreadsheet sourcing now lives in the backend.
 */
export const EVENT_CONFIGS: Record<string, EventConfig> = {
  ...configsFrom2025To2024,
  ...configsFrom2023To2022,
  ...configsFrom2021To2020,
};
