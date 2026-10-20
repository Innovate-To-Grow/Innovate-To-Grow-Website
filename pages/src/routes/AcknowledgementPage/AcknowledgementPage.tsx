import {CMSPageComponent} from '@/features/cms';

/**
 * /acknowledgement is an ordinary CMS page (its copy and sponsor-year blocks are edited in the CMS);
 * the router's CMS catch-all serves it. This wrapper renders that page where a component is needed
 * by route, as in the embed-widget registry.
 */
export const AcknowledgementPage = () => <CMSPageComponent routeOverride="/acknowledgement" />;
