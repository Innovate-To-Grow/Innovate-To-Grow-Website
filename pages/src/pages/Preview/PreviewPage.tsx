import { useEffect, useState } from 'react';
import { ComponentListRenderer } from '../../components/PageContent/ComponentRenderer';
import type { PageComponent } from '../../services/api';

export const PreviewPage = () => {
  const [components, setComponents] = useState<PageComponent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === 'preview-update-data') {
        // Cast or map data to PageComponent type
        const rawComponents = event.data.components || [];
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        const mappedComponents = rawComponents.map((c: any) => ({
            ...c,
            // Handle string ID if needed, ensure it's a number or compatible
            id: typeof c.id === 'string' ? parseInt(c.id.replace('preview-', '')) || Math.random() : c.id,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
        }));
        setComponents(mappedComponents);
        setConnected(true);
      }
    };
    window.addEventListener('message', handleMessage);
    
    // Signal readiness
    if (window.opener) {
        window.opener.postMessage({ type: 'preview-ready' }, '*');
    }

    return () => window.removeEventListener('message', handleMessage);
  }, []);

  if (!connected && components.length === 0) {
    return (
        <div style={{ padding: 40, textAlign: 'center', color: '#666' }}>
            <h2>Waiting for content...</h2>
            <p>Make changes in the editor to see live preview.</p>
        </div>
    );
  }

  return (
    <div className="preview-container">
       <ComponentListRenderer components={components} />
    </div>
  );
};
