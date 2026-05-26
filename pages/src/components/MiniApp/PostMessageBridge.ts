import {
  createMiniAppRecord,
  deleteMiniAppRecord,
  getMiniAppRecord,
  listMiniAppRecords,
  updateMiniAppRecord,
} from '../../features/miniapps/api';
import { authApi } from '../../shared/auth/client';

export interface MiniAppRequest {
  type: 'itg-miniapp-request';
  id: string;
  action: string;
  params: Record<string, unknown>;
}

export interface MiniAppResizeEvent {
  type: 'itg-miniapp-resize';
  height: number;
}

export type MiniAppMessage = MiniAppRequest | MiniAppResizeEvent;

export interface BridgeCallbacks {
  onResize: (height: number) => void;
  onNavigate: (path: string) => void;
  getUser: () => { id: string; email: string; name: string } | null;
}

export function isMiniAppMessage(data: unknown): data is MiniAppMessage {
  if (!data || typeof data !== 'object') return false;
  const msg = data as Record<string, unknown>;
  return msg.type === 'itg-miniapp-request' || msg.type === 'itg-miniapp-resize';
}

export function createPostMessageBridge(slug: string, iframeRef: React.RefObject<HTMLIFrameElement | null>, callbacks: BridgeCallbacks) {
  async function handleRequest(request: MiniAppRequest): Promise<unknown> {
    const { action, params } = request;

    switch (action) {
      case 'api.list':
        return listMiniAppRecords(slug, params as Record<string, string>);

      case 'api.get':
        return getMiniAppRecord(slug, params.id as string);

      case 'api.create':
        return createMiniAppRecord(slug, params.data as Record<string, unknown>);

      case 'api.update':
        return updateMiniAppRecord(slug, params.id as string, params.data as Record<string, unknown>);

      case 'api.delete':
        await deleteMiniAppRecord(slug, params.id as string);
        return { ok: true };

      case 'auth.getUser':
        return callbacks.getUser();

      case 'navigate':
        callbacks.onNavigate(params.path as string);
        return { ok: true };

      case 'fetch': {
        const url = params.url as string;
        if (!url || typeof url !== 'string') throw new Error('Invalid URL');
        if (url.startsWith('http://') || url.startsWith('https://') || url.startsWith('//')) {
          throw new Error('Direct external requests not allowed. Use relative API paths.');
        }
        if (url.startsWith('/admin')) {
          throw new Error('Admin endpoints are not accessible from mini-apps.');
        }
        const options = (params.options as Record<string, unknown>) || {};
        const response = await authApi.request({
          url,
          method: (options.method as string) || 'GET',
          data: options.body,
          headers: options.headers as Record<string, string>,
        });
        return response.data;
      }

      default:
        throw new Error(`Unknown action: ${action}`);
    }
  }

  function handleMessage(event: MessageEvent) {
    const data = event.data;
    if (!isMiniAppMessage(data)) return;

    if (!iframeRef.current || event.source !== iframeRef.current.contentWindow) return;

    if (data.type === 'itg-miniapp-resize') {
      callbacks.onResize(data.height);
      return;
    }

    if (data.type === 'itg-miniapp-request') {
      handleRequest(data).then(
        (result) => {
          iframeRef.current?.contentWindow?.postMessage(
            { type: 'itg-miniapp-response', id: data.id, data: result },
            '*'
          );
        },
        (error) => {
          iframeRef.current?.contentWindow?.postMessage(
            { type: 'itg-miniapp-response', id: data.id, error: error.message || 'Unknown error' },
            '*'
          );
        }
      );
    }
  }

  window.addEventListener('message', handleMessage);
  return () => window.removeEventListener('message', handleMessage);
}
