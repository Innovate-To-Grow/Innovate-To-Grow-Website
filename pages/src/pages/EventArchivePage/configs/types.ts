import type {ClassConfig} from '../../../components/ScheduleGrid';

export interface EventConfig {
  title: string;
  semester: string;
  classes: ClassConfig[];
}
