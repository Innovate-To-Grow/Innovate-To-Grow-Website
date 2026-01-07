"""
Google Sheets service for fetching past projects data.
"""

import os
import logging
from typing import List, Dict, Any, Optional
from django.conf import settings
import gspread
from google.oauth2 import service_account
import requests

logger = logging.getLogger(__name__)


class GoogleSheetsService:
    """
    Service for fetching and transforming past projects data from Google Sheets.
    
    Authentication priority:
    1. GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE environment variable (if set)
    2. Default location: ~/.config/gspread/service_account.json (if exists)
    3. GOOGLE_SHEETS_API_KEY environment variable (public API access)
    
    Supports both service account authentication (recommended) and public API key
    access (read-only, for public sheets).
    """

    def __init__(self):
        """
        Initialize the Google Sheets service.
        
        Service account file is loaded from settings, which checks:
        - GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE env var first
        - Default location (~/.config/gspread/service_account.json) if env var not set
        - None if neither exists (will fall back to API key)
        """
        self.spreadsheet_id = getattr(
            settings,
            'GOOGLE_SHEETS_SPREADSHEET_ID',
            '1KATiK1Fnlb7Vsd186mCbaGjhID-OUGN-1QHWY8hIc5U'
        )
        self.worksheet_name = getattr(
            settings,
            'GOOGLE_SHEETS_WORKSHEET_NAME',
            'Past-Projects-WEB-LIVE'
        )
        self.api_key = getattr(settings, 'GOOGLE_SHEETS_API_KEY', None)
        self.service_account_file = getattr(
            settings,
            'GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE',
            None
        )

    def _get_client(self) -> gspread.Client:
        """
        Get authenticated gspread client.
        
        Tries service account first, then falls back to public API key.
        """
        if self.service_account_file and os.path.exists(self.service_account_file):
            try:
                creds = service_account.Credentials.from_service_account_file(
                    self.service_account_file,
                    scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
                )
                return gspread.authorize(creds)
            except Exception as e:
                logger.warning(f"Failed to use service account: {e}")
        
        # Fall back to public API key (read-only)
        # Note: gspread doesn't directly support API key auth for private sheets
        # For public sheets, we can use the public URL with API key
        # For now, we'll use service account or try to open as public
        if self.api_key:
            # If we have an API key, we'll use the public API endpoint directly
            # This is handled in fetch_past_projects method
            pass
        
        # Try to open as public (will work if sheet is public)
        try:
            # For public sheets, we can use gspread without auth
            # But we need to use the public API endpoint
            # This will be handled in fetch_past_projects
            raise Exception("Service account file required for private sheets")
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets: {e}")
            raise

    def fetch_past_projects(self) -> List[Dict[str, Any]]:
        """
        Fetch past projects data from Google Sheets and transform to structured format.
        
        Returns:
            List of project dictionaries with keys:
            - Year-Semester
            - Class
            - Team#
            - Team Name
            - Project Title
            - Organization
            - Industry
            - Abstract
            - Student Names
        
        Raises:
            Exception: If unable to fetch or parse data from Google Sheets.
        """
        try:
            all_values = None
            
            # Try to use service account first (from env var or default location)
            if self.service_account_file and os.path.exists(self.service_account_file):
                try:
                    creds = service_account.Credentials.from_service_account_file(
                        self.service_account_file,
                        scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
                    )
                    client = gspread.authorize(creds)
                    spreadsheet = client.open_by_key(self.spreadsheet_id)
                    worksheet = spreadsheet.worksheet(self.worksheet_name)
                    all_values = worksheet.get_all_values()
                except Exception as e:
                    logger.warning(f"Service account failed, trying public API: {e}")
            
            # Fall back to public API endpoint if service account failed or not available
            if all_values is None:
                if self.api_key:
                    url = f"https://sheets.googleapis.com/v4/spreadsheets/{self.spreadsheet_id}/values/{self.worksheet_name}"
                    params = {'key': self.api_key}
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    data = response.json()
                    all_values = data.get('values', [])
                else:
                    raise Exception("No authentication method available. Please configure GOOGLE_SHEETS_SERVICE_ACCOUNT_FILE or GOOGLE_SHEETS_API_KEY")
            
            if not all_values:
                logger.warning("Google Sheets worksheet is empty")
                return []
            
            # Skip header row if present
            header_row = all_values[0] if all_values else []
            data_rows = all_values[1:] if len(all_values) > 1 else []
            
            # Transform array data to structured objects
            projects = []
            for row in data_rows:
                if not row or len(row) < 9:
                    # Skip incomplete rows
                    continue
                
                # Normalize Year-Semester (remove class suffixes)
                year_semester = row[0].strip() if len(row) > 0 and row[0] else ''
                if year_semester:
                    # Remove suffixes like -EngSL, -CSE, -CAP, -CAP1, -CEE
                    for suffix in ['-EngSL', '-CSE', '-CAP', '-CAP1', '-CEE']:
                        if year_semester.endswith(suffix):
                            year_semester = year_semester[:-len(suffix)]
                            break
                
                project = {
                    "Year-Semester": year_semester,
                    "Class": row[1].strip() if len(row) > 1 and row[1] else '',
                    "Team#": row[2].strip() if len(row) > 2 and row[2] else '',
                    "Team Name": row[3].strip() if len(row) > 3 and row[3] else '',
                    "Project Title": row[4].strip() if len(row) > 4 and row[4] else '',
                    "Organization": row[5].strip() if len(row) > 5 and row[5] else '',
                    "Industry": row[6].strip() if len(row) > 6 and row[6] else '',
                    "Abstract": row[7].strip() if len(row) > 7 and row[7] else '',
                    "Student Names": row[8].strip() if len(row) > 8 and row[8] else '',
                }
                
                # Only add projects with at least a team name or project title
                if project["Team Name"] or project["Project Title"]:
                    projects.append(project)
            
            logger.info(f"Successfully fetched {len(projects)} past projects from Google Sheets")
            return projects
            
        except gspread.exceptions.APIError as e:
            logger.error(f"Google Sheets API error: {e}")
            raise Exception(f"Unable to fetch data from Google Sheets: {str(e)}")
        except Exception as e:
            logger.error(f"Error fetching past projects: {e}")
            raise Exception(f"Error fetching past projects: {str(e)}")


# Singleton instance
_google_sheets_service: Optional[GoogleSheetsService] = None


def get_google_sheets_service() -> GoogleSheetsService:
    """Get or create the Google Sheets service instance."""
    global _google_sheets_service
    if _google_sheets_service is None:
        _google_sheets_service = GoogleSheetsService()
    return _google_sheets_service

