import api from '../../shared/api/client';

export interface Sponsor {
  id: string;
  name: string;
  logo: string | null;
  website: string;
}

export interface SponsorYear {
  year: number;
  sponsors: Sponsor[];
}

export const fetchSponsors = async (): Promise<SponsorYear[]> => {
  const response = await api.get<SponsorYear[]>('/sponsors/');
  return response.data;
};
