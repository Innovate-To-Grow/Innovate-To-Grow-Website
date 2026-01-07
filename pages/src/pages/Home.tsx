import { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { fetchSiteSettings, type SiteSettings } from '../services/api';
import { HomePreEvent } from './HomePreEvent';
import { HomeDuringSemester } from './HomeDuringSemester';
import './Home.css';

export const Home = () => {
  const [siteSettings, setSiteSettings] = useState<SiteSettings | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadSiteSettings = async () => {
      setLoading(true);
      setError(null);
      try {
        const settings = await fetchSiteSettings();
        setSiteSettings(settings);
      } catch (err) {
        setError('Unable to load site settings.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadSiteSettings();
  }, []);

  if (loading) {
    return (
      <div className="home-container">
        <div className="home-state">Loading...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="home-container">
        <div className="home-state home-error">{error}</div>
      </div>
    );
  }

  if (!siteSettings) {
    return null;
  }

  // Render the appropriate component based on home_page_mode
  switch (siteSettings.home_page_mode) {
    case 'pre_event':
      return <HomePreEvent />;
    case 'during_semester':
      return <HomeDuringSemester />;
    case 'event':
      return <Navigate to="/event" replace />;
    default:
      return <HomePreEvent />;
  }
};
