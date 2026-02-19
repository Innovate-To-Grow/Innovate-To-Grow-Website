import { useEffect, useState, useRef, useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ComponentListRenderer } from '../../components/PageContent/ComponentRenderer';
import { type PageComponent, validatePreviewToken, fetchPreviewData } from '../../services/api';

export const PreviewPage = () => {
  const [components, setComponents] = useState<PageComponent[]>([]);
  const [connected, setConnected] = useState(false);
  const [isValidToken, setIsValidToken] = useState<boolean | null>(null);
  const [errorDetail, setErrorDetail] = useState('');
  const [searchParams] = useSearchParams();
  const lastTimestamp = useRef(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const sessionId = searchParams.get('sessionId');
  const token = searchParams.get('token');
  const objectId = searchParams.get('objectId');

  // Derive missing-param errors without setState in effect
  const missingParam = !token ? 'Missing preview token.' : !sessionId ? 'Missing session id.' : null;

  useEffect(() => {
    if (missingParam || !token) return;

    let cancelled = false;
    const check = async () => {
      const valid = await validatePreviewToken(token, objectId || undefined);
      if (cancelled) return;
      setIsValidToken(valid);
      if (!valid) {
        setErrorDetail('Invalid or expired preview token.');
      }
    };
    check();
    return () => { cancelled = true; };
  }, [token, objectId, sessionId, missingParam]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const applyComponents = useCallback((rawComponents: any[]) => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const mapped = rawComponents.map((c: any) => ({
      ...c,
      id: typeof c.id === 'string' ? parseInt(c.id.replace('preview-', '')) || Math.random() : c.id,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }));
    setComponents(mapped);
    setConnected(true);
  }, []);

  useEffect(() => {
    if (isValidToken !== true || !sessionId) return;

    const poll = async () => {
      const data = await fetchPreviewData(sessionId);
      if (data && data.timestamp > lastTimestamp.current) {
        lastTimestamp.current = data.timestamp;
        applyComponents(data.components);
      }
    };

    poll();
    pollRef.current = setInterval(poll, 1000);

    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [isValidToken, sessionId, applyComponents]);

  if (missingParam) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#dc2626' }}>
        <h2>Unauthorized</h2>
        <p>{missingParam}</p>
      </div>
    );
  }

  if (isValidToken === null) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#666' }}>
        <h2>Verifying...</h2>
      </div>
    );
  }

  if (isValidToken === false) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#dc2626' }}>
        <h2>Unauthorized</h2>
        <p>{errorDetail}</p>
      </div>
    );
  }

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
