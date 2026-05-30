import type {ClassConfig} from '@/features/events/components/ScheduleGrid';

export interface EventConfig {
  title: string;
  semester: string;
  classes: ClassConfig[];
}
