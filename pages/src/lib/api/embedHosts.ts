import {api} from './api-client';

export interface CMSEmbedHostsResponse {
  hosts: string[];
  revision: string;
}

/** The iframe hosts CMS content may embed (admin-managed); `SafeHtml` allows only these. */
export async function fetchCMSEmbedHosts(): Promise<CMSEmbedHostsResponse> {
  const response = await api.get<CMSEmbedHostsResponse>('/cms/embed-hosts/');
  return response.data;
}
