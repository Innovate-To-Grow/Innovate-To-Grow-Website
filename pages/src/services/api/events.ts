import api from './client';

// ======================== Event Types ========================

export interface Presentation {
  order: number;
  team_id: string;
  team_name: string;
  project_title: string;
  organization: string;
}

export interface Track {
  track_name: string;
  room: string;
  start_time: string | null;
  presentations: Presentation[];
}

export interface Program {
  program_name: string;
  tracks: Track[];
}

export interface TrackWinner {
  track_name: string;
  winner_name: string;
}

export interface SpecialAward {
  program_name: string;
  award_winner: string;
}

export interface ExpoRow {
  time: string;
  room: string;
  description: string;
}

export interface ReceptionRow {
  time: string;
  room: string;
  description: string;
}

export interface EventData {
  event_uuid: string;
  event_name: string;
  event_date: string; // ISO date string
  event_time: string; // ISO time string
  upper_bullet_points: string[]; // Markdown strings
  lower_bullet_points: string[]; // Markdown strings
  expo_table: ExpoRow[];
  reception_table: ReceptionRow[];
  is_published: boolean;
  programs: Program[];
  track_winners: TrackWinner[];
  special_awards: SpecialAward[];
  created_at: string;
  updated_at: string;
}

export const fetchEvent = async (): Promise<EventData> => {
  const response = await api.get<EventData>('/events/');
  return response.data;
};
