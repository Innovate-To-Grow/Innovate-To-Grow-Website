import {useState} from 'react';

interface DetailsToggles {
  allDetailsExpanded: boolean;
  onToggleExpanded: (rowKey: string) => void;
  onToggleAllDetails?: () => void;
}

/**
 * Who tells a screen reader about opened details. A row opened by its own button reports its loading (and a
 * failure) itself. Rows opened all at once (View All Details, or a list that starts with every row open) stay
 * quiet, or a whole page of "Loading project details…" would be read out one by one; the grid says once that
 * every row is open.
 */
export function useDetailsAnnouncements({allDetailsExpanded, onToggleExpanded, onToggleAllDetails}: DetailsToggles) {
  const [openedOneByOne, setOpenedOneByOne] = useState(false);
  const [message, setMessage] = useState('');

  const toggleRow = (rowKey: string) => {
    setOpenedOneByOne(true);
    onToggleExpanded(rowKey);
  };

  const toggleAllDetails = () => {
    setOpenedOneByOne(false);
    setMessage(allDetailsExpanded ? 'All details hidden.' : 'All details shown.');
    onToggleAllDetails?.();
  };

  return {announceRows: openedOneByOne, message, toggleRow, toggleAllDetails};
}
