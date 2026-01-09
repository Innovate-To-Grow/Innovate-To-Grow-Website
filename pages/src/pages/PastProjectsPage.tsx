/**
 * Past Projects Page - Main component for searching, filtering, merging, and sharing past projects.
 */

import { useState, useEffect, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { fetchPastProjects, createSharedURL, fetchSharedURL, type PastProject, type SharedProjectURLData } from '../services/api';
import { SearchTable } from '../components/PastProjects/SearchTable';
import { EnhancedDataTable } from '../components/PastProjects/EnhancedDataTable';
import './PastProjectsPage.css';

interface SearchTableState {
  id: string;
  keptProjects: PastProject[];
  deletedProjects: PastProject[];
}

export const PastProjectsPage = () => {
  const { uuid } = useParams<{ uuid?: string }>();
  const [allProjects, setAllProjects] = useState<PastProject[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchTables, setSearchTables] = useState<SearchTableState[]>([]);
  const [mergedProjects, setMergedProjects] = useState<PastProject[]>([]);
  const [sharedURLData, setSharedURLData] = useState<SharedProjectURLData | null>(null);
  const [shareURL, setShareURL] = useState<string | null>(null);
  const [shareLoading, setShareLoading] = useState(false);
  const [shareError, setShareError] = useState<string | null>(null);
  const [searchTableCounter, setSearchTableCounter] = useState(1);

  const isSharedView = !!uuid;

  // Load projects data
  useEffect(() => {
    const loadProjects = async () => {
      setLoading(true);
      setError(null);
      try {
        const projects = await fetchPastProjects();
        setAllProjects(projects);
      } catch (err) {
        setError('Unable to load past projects. Please try again later.');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    loadProjects();
  }, []);

  // Generate a unique key for a project (must be defined before useEffect)
  const getProjectKey = (project: PastProject): string => {
    return JSON.stringify({
      'Year-Semester': project['Year-Semester'] || '',
      'Class': project['Class'] || '',
      'Team#': project['Team#'] || '',
      'Team Name': project['Team Name'] || '',
      'Project Title': project['Project Title'] || '',
    });
  };

  // Load shared URL data if viewing shared URL
  useEffect(() => {
    if (uuid && allProjects.length > 0) {
      const loadSharedURL = async () => {
        try {
          const data = await fetchSharedURL(uuid);
          
          // #region agent log
          fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:57',message:'loadSharedURL: data received from backend',data:{hasProjectKeys:!!data.project_keys,projectKeysCount:data.project_keys?.length||0,teamNamesCount:data.team_names.length,teamNumbersCount:data.team_numbers.length,teamNames:data.team_names.slice(0,5),teamNumbers:data.team_numbers.slice(0,5),projectKeys:data.project_keys?.slice(0,3)},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'B'})}).catch(()=>{});
          // #endregion
          
          setSharedURLData(data);

          // Filter projects using project_keys if available (precise matching)
          // Otherwise fall back to team names/numbers (less precise)
          let filtered: PastProject[];
          
          if (data.project_keys && data.project_keys.length > 0) {
            // Use project keys for precise matching
            const projectKeysSet = new Set(data.project_keys);
            
            // #region agent log
            fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:66',message:'loadSharedURL: using project_keys matching',data:{projectKeysSetSize:projectKeysSet.size,allProjectsCount:allProjects.length},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'B'})}).catch(()=>{});
            // #endregion
            
            filtered = allProjects.filter((project) => {
              const key = getProjectKey(project);
              const matches = projectKeysSet.has(key);
              
              // #region agent log
              if (filtered && filtered.length < 10) {
                fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:72',message:'loadSharedURL: project key check',data:{key:key.substring(0,100),matches:matches,'Year-Semester':project['Year-Semester'],'Team Name':project['Team Name'],'Team#':project['Team#']},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'B'})}).catch(()=>{});
              }
              // #endregion
              
              return matches;
            });
          } else {
            // Fallback: filter by team names and numbers (AND logic for better precision)
            // A project must match BOTH a team name AND team number from the shared list
            const teamNamesSet = new Set(data.team_names);
            const teamNumbersSet = new Set(data.team_numbers);
            
            // #region agent log
            fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:82',message:'loadSharedURL: using team names/numbers matching (fallback)',data:{teamNamesSetSize:teamNamesSet.size,teamNumbersSetSize:teamNumbersSet.size,allProjectsCount:allProjects.length},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'B'})}).catch(()=>{});
            // #endregion
            
            filtered = allProjects.filter((project) => {
              const teamName = project['Team Name'] || '';
              const teamNumber = project['Team#'] || '';
              // Match if both team name and number are in the shared lists
              // OR if we only have one type of identifier
              let matches = false;
              if (teamNamesSet.size > 0 && teamNumbersSet.size > 0) {
                matches = teamNamesSet.has(teamName) && teamNumbersSet.has(teamNumber);
              } else if (teamNamesSet.size > 0) {
                matches = teamNamesSet.has(teamName);
              } else if (teamNumbersSet.size > 0) {
                matches = teamNumbersSet.has(teamNumber);
              }
              return matches;
            });
          }

          // #region agent log
          fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:99',message:'loadSharedURL: filtered results',data:{filteredCount:filtered.length,filteredProjects:filtered.slice(0,5).map(p=>({'Year-Semester':p['Year-Semester'],'Class':p['Class'],'Team#':p['Team#'],'Team Name':p['Team Name'],'Project Title':p['Project Title']}))},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'B'})}).catch(()=>{});
          // #endregion

          setMergedProjects(filtered);
        } catch (err) {
          setError('Unable to load shared results. The link may be invalid or expired.');
          console.error(err);
        }
      };

      loadSharedURL();
    }
  }, [uuid, allProjects]);

  // Add a new search table
  const addSearchTable = () => {
    const newId = `table-${searchTableCounter}`;
    setSearchTables((prev) => [
      ...prev,
      {
        id: newId,
        keptProjects: [],
        deletedProjects: [],
      },
    ]);
    setSearchTableCounter((prev) => prev + 1);
  };

  // Delete a search table
  const deleteSearchTable = (tableId: string) => {
    setSearchTables((prev) => prev.filter((table) => table.id !== tableId));
  };

  // Handle keeping selected rows from a search table
  const handleKeepSelected = (tableId: string, projects: PastProject[]) => {
    setSearchTables((prev) =>
      prev.map((table) =>
        table.id === tableId
          ? { ...table, keptProjects: projects }
          : table
      )
    );
  };

  // Handle deleting selected rows from a search table
  const handleDeleteSelected = (tableId: string, projects: PastProject[]) => {
    setSearchTables((prev) =>
      prev.map((table) =>
        table.id === tableId
          ? { ...table, deletedProjects: [...table.deletedProjects, ...projects] }
          : table
      )
    );
  };

  // Merge results from all search tables
  const handleMergeResults = () => {
    const allKeptProjects: PastProject[] = [];
    const allDeletedProjects: PastProject[] = [];

    // Collect all kept and deleted projects
    searchTables.forEach((table) => {
      allKeptProjects.push(...table.keptProjects);
      allDeletedProjects.push(...table.deletedProjects);
    });

    // Create a set of deleted project keys for quick lookup
    const deletedKeys = new Set(
      allDeletedProjects.map((p) =>
        JSON.stringify({
          'Year-Semester': p['Year-Semester'],
          'Class': p['Class'],
          'Team#': p['Team#'],
          'Team Name': p['Team Name'],
          'Project Title': p['Project Title'],
          'Organization': p['Organization'],
          'Industry': p['Industry'],
          'Abstract': p['Abstract'],
          'Student Names': p['Student Names'],
        })
      )
    );

    // Filter out deleted projects
    const filteredKept = allKeptProjects.filter(
      (p) =>
        !deletedKeys.has(
          JSON.stringify({
            'Year-Semester': p['Year-Semester'],
            'Class': p['Class'],
            'Team#': p['Team#'],
            'Team Name': p['Team Name'],
            'Project Title': p['Project Title'],
            'Organization': p['Organization'],
            'Industry': p['Industry'],
            'Abstract': p['Abstract'],
            'Student Names': p['Student Names'],
          })
        )
    );

    // Deduplicate by comparing all fields
    const uniqueProjects = new Map<string, PastProject>();
    filteredKept.forEach((project) => {
      const key = JSON.stringify({
        'Year-Semester': project['Year-Semester'],
        'Class': project['Class'],
        'Team#': project['Team#'],
        'Team Name': project['Team Name'],
        'Project Title': project['Project Title'],
        'Organization': project['Organization'],
        'Industry': project['Industry'],
        'Abstract': project['Abstract'],
        'Student Names': project['Student Names'],
      });
      if (!uniqueProjects.has(key)) {
        uniqueProjects.set(key, project);
      }
    });

    setMergedProjects(Array.from(uniqueProjects.values()));
  };

  // Share merged results
  const handleShareResults = async () => {
    if (mergedProjects.length === 0) {
      setShareError('No projects to share. Please merge some results first.');
      return;
    }

    setShareLoading(true);
    setShareError(null);

    try {
      // #region agent log
      fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:233',message:'handleShareResults: mergedProjects count',data:{mergedProjectsCount:mergedProjects.length,mergedProjects:mergedProjects.map(p=>({'Year-Semester':p['Year-Semester'],'Class':p['Class'],'Team#':p['Team#'],'Team Name':p['Team Name'],'Project Title':p['Project Title']}))},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A'})}).catch(()=>{});
      // #endregion
      
      // Generate unique keys for each project to share
      const projectKeys = mergedProjects
        .map(getProjectKey)
        .filter((key) => key && key.trim());

      // #region agent log
      fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:240',message:'handleShareResults: projectKeys generated',data:{projectKeysCount:projectKeys.length,projectKeys:projectKeys.slice(0,5)},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A'})}).catch(()=>{});
      // #endregion

      // Also extract team names and numbers for backward compatibility
      // but we'll use project keys for precise matching
      const teamNames = mergedProjects
        .map((p) => p['Team Name'])
        .filter((name) => name && name.trim())
        .filter((value, index, self) => self.indexOf(value) === index); // Unique

      const teamNumbers = mergedProjects
        .map((p) => p['Team#'])
        .filter((num) => num && num.trim())
        .filter((value, index, self) => self.indexOf(value) === index); // Unique

      // #region agent log
      fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:254',message:'handleShareResults: request payload',data:{teamNamesCount:teamNames.length,teamNames:teamNames,teamNumbersCount:teamNumbers.length,teamNumbers:teamNumbers,projectKeysCount:projectKeys.length},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A'})}).catch(()=>{});
      // #endregion

      const response = await createSharedURL({
        team_names: teamNames,
        team_numbers: teamNumbers,
        project_keys: projectKeys, // Add project keys for precise matching
      });

      // #region agent log
      fetch('http://127.0.0.1:7243/ingest/4d26f42c-4d1e-4ce2-a9cd-89456700c2b1',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'PastProjectsPage.tsx:262',message:'handleShareResults: response received',data:{uuid:response.uuid,url:response.url},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A'})}).catch(()=>{});
      // #endregion

      setShareURL(response.url);
    } catch (err) {
      setShareError('Unable to create shareable URL. Please try again.');
      console.error(err);
    } finally {
      setShareLoading(false);
    }
  };

  // Copy share URL to clipboard
  const copyShareURL = async () => {
    if (shareURL) {
      try {
        await navigator.clipboard.writeText(shareURL);
        alert('URL copied to clipboard!');
      } catch (err) {
        console.error('Failed to copy URL:', err);
        alert('Failed to copy URL. Please copy it manually.');
      }
    }
  };

  if (loading) {
    return (
      <div className="past-projects-container">
        <div className="past-projects-state">Loading past projects...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="past-projects-container">
        <div className="past-projects-state past-projects-error">{error}</div>
      </div>
    );
  }

  return (
    <div className="past-projects-container">
      <h1 className="past-projects-title">Past Projects</h1>

      {isSharedView && (
        <div className="shared-view-indicator">
          <p>You are viewing shared results. This view is read-only.</p>
          {sharedURLData && (
            <p className="shared-view-meta">
              Shared on {new Date(sharedURLData.created_at).toLocaleDateString()}
            </p>
          )}
        </div>
      )}

      {!isSharedView && (
        <>
          <div className="past-projects-instructions">
            <h2>How to Use</h2>
            <ol>
              <li>Create one or more search tables to filter projects</li>
              <li>Select rows you want to keep or delete</li>
              <li>Click "Save/Merge Results" to combine kept rows from all tables</li>
              <li>Click "Get Shareable URL" to create a shareable link</li>
            </ol>
          </div>

          {/* Search Tables Section */}
          <div className="search-tables-section">
            <div className="section-header">
              <h2>Search Tables</h2>
              <button
                type="button"
                className="add-table-btn"
                onClick={addSearchTable}
                aria-label="Add new search table"
              >
                + Search Table
              </button>
            </div>

            {searchTables.length === 0 && (
              <div className="no-tables-message">
                <p>No search tables yet. Click "+ Search Table" to create one.</p>
              </div>
            )}

            {searchTables.map((table) => (
              <SearchTable
                key={table.id}
                tableId={table.id}
                allProjects={allProjects}
                onKeepSelected={(projects) => handleKeepSelected(table.id, projects)}
                onDeleteSelected={(projects) => handleDeleteSelected(table.id, projects)}
                onDeleteTable={() => deleteSearchTable(table.id)}
                readOnly={false}
              />
            ))}
          </div>

          {/* Merge Section */}
          {searchTables.length > 0 && (
            <div className="merge-section">
              <div className="section-header">
                <h2>Merge Results</h2>
                <button
                  type="button"
                  className="merge-btn"
                  onClick={handleMergeResults}
                  aria-label="Merge results from all search tables"
                >
                  Save/Merge Results
                </button>
              </div>
              <p className="section-description">
                This will combine all kept rows from your search tables and remove duplicates.
              </p>
            </div>
          )}

          {/* Merged Results Section */}
          {mergedProjects.length > 0 && (
            <div className="merged-results-section">
              <div className="section-header">
                <h2>Merged Results ({mergedProjects.length} projects)</h2>
                <button
                  type="button"
                  className="share-btn"
                  onClick={handleShareResults}
                  disabled={shareLoading}
                  aria-label="Get shareable URL"
                >
                  {shareLoading ? 'Creating...' : 'Get Shareable URL'}
                </button>
              </div>

              {shareError && (
                <div className="share-error">{shareError}</div>
              )}

              {shareURL && (
                <div className="share-url-section">
                  <p className="share-url-label">Shareable URL:</p>
                  <div className="share-url-container">
                    <input
                      type="text"
                      readOnly
                      value={shareURL}
                      className="share-url-input"
                      aria-label="Shareable URL"
                    />
                    <button
                      type="button"
                      className="copy-url-btn"
                      onClick={copyShareURL}
                      aria-label="Copy URL to clipboard"
                    >
                      Copy URL
                    </button>
                  </div>
                </div>
              )}

              <EnhancedDataTable
                projects={mergedProjects}
                showSelection={false}
                showExport={true}
                readOnly={false}
              />
            </div>
          )}
        </>
      )}

      {/* Shared View - Show merged results */}
      {isSharedView && mergedProjects.length > 0 && (
        <div className="shared-results-section">
          <h2>Shared Results ({mergedProjects.length} projects)</h2>
          <EnhancedDataTable
            projects={mergedProjects}
            showSelection={false}
            showExport={true}
            readOnly={true}
          />
        </div>
      )}

      {isSharedView && mergedProjects.length === 0 && !loading && (
        <div className="past-projects-state">
          No projects found for this shared URL.
        </div>
      )}
    </div>
  );
};

