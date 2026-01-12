"""
Google Sheets sync service for Members, Prospects, and Event Registrations.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from django.conf import settings
from django.utils import timezone
import gspread
from gspread.http_client import BackOffHTTPClient

from ..models import Member, Prospect
from events.models import Event, EventRegistration
from .member_serialization import (
    member_to_row,
    prospect_to_row,
    row_to_prospect,
)
from .collision_detection import update_prospect_collisions

logger = logging.getLogger(__name__)


class MemberSyncService:
    """
    Service for syncing Members, Prospects, and Event Registrations with Google Sheets.
    
    Uses service account authentication from ~/.config/gspread/service_account.json
    with BackOffHTTPClient for automatic retry logic.
    """

    # Members tab column headers
    MEMBERS_HEADERS = [
        "Order",
        "First Name",
        "Last Name",
        "When Started",
        "Last Updated",
        "Primary Email",
        "Primary Verified",
        "Primary Subscribed",
        "Primary Expired",
        "Primary Bounced",
        "Secondary Email",
        "Secondary Verified",
        "Secondary Subscribed",
        "Secondary Expired",
        "Secondary Bounced",
        "Phone Number",
        "Phone number subscribed",
        "Phone number verified",
        "Info Completed",
    ]

    # Prospects tab column headers
    PROSPECTS_HEADERS = [
        "First Name (optional)",
        "Last Name (optional)",
        "Email",
        "When Input?",
        "When signed up as member?",
        "When last checked?",
        "Bounced (when)?",
        "Collision?",
        "Secondary Email (optional)",
        "Secondary Bounced (when)?",
        "Secondary Collision",
        "Phone Number (optional)",
        "Phone Bounced (when)?",
        "Phone Collision",
        "Notes",
    ]

    def __init__(self):
        """Initialize the sync service."""
        self.spreadsheet_id = getattr(
            settings,
            'GOOGLE_SHEETS_MEMBERS_SPREADSHEET_ID',
            None
        )
        if not self.spreadsheet_id:
            raise ValueError("GOOGLE_SHEETS_MEMBERS_SPREADSHEET_ID must be set in settings")
        
        # Service account file path
        self.service_account_path = Path.home() / '.config' / 'gspread' / 'service_account.json'
        
        if not self.service_account_path.exists():
            raise FileNotFoundError(
                f"Service account file not found at {self.service_account_path}. "
                "Please place your service_account.json file there."
            )

    def _get_client(self) -> gspread.Client:
        """
        Get authenticated gspread client with BackOffHTTPClient for retry logic.
        """
        try:
            # Use service_account with BackOffHTTPClient for automatic retry on rate limits
            return gspread.service_account(
                filename=str(self.service_account_path),
                http_client=BackOffHTTPClient
            )
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets: {e}")
            raise

    def _get_spreadsheet(self) -> gspread.Spreadsheet:
        """Get the spreadsheet instance."""
        client = self._get_client()
        return client.open_by_key(self.spreadsheet_id)

    def ensure_sheet_structure(self) -> None:
        """
        Ensure the Google Sheet has the required tabs and headers.
        Creates them if they don't exist.
        """
        spreadsheet = self._get_spreadsheet()
        existing_worksheets = [ws.title for ws in spreadsheet.worksheets()]
        
        # Ensure Members tab exists
        if "Members" not in existing_worksheets:
            logger.info("Creating Members tab")
            members_ws = spreadsheet.add_worksheet("Members", rows=1000, cols=20)
            members_ws.append_row(self.MEMBERS_HEADERS)
        else:
            members_ws = spreadsheet.worksheet("Members")
            # Check if headers exist
            existing_headers = members_ws.row_values(1)
            if not existing_headers or existing_headers != self.MEMBERS_HEADERS:
                # Update headers
                members_ws.update('A1', [self.MEMBERS_HEADERS])
        
        # Ensure Prospects tab exists
        if "Prospects" not in existing_worksheets:
            logger.info("Creating Prospects tab")
            prospects_ws = spreadsheet.add_worksheet("Prospects", rows=1000, cols=20)
            prospects_ws.append_row(self.PROSPECTS_HEADERS)
        else:
            prospects_ws = spreadsheet.worksheet("Prospects")
            # Check if headers exist
            existing_headers = prospects_ws.row_values(1)
            if not existing_headers or existing_headers != self.PROSPECTS_HEADERS:
                # Update headers
                prospects_ws.update('A1', [self.PROSPECTS_HEADERS])

    def get_or_create_event_tab(self, event: Event) -> gspread.Worksheet:
        """
        Get or create a tab for a specific event.
        Tab name will be the event slug or event name.
        """
        spreadsheet = self._get_spreadsheet()
        tab_name = event.slug or event.event_name
        
        try:
            worksheet = spreadsheet.worksheet(tab_name)
            # Verify headers
            existing_headers = worksheet.row_values(1)
            if not existing_headers or existing_headers != self.MEMBERS_HEADERS:
                worksheet.update('A1', [self.MEMBERS_HEADERS])
            return worksheet
        except gspread.WorksheetNotFound:
            logger.info(f"Creating event tab: {tab_name}")
            worksheet = spreadsheet.add_worksheet(tab_name, rows=1000, cols=20)
            worksheet.append_row(self.MEMBERS_HEADERS)
            return worksheet

    def sync_members_to_sheet(self) -> Dict[str, Any]:
        """
        Sync all Members from database to Google Sheets Members tab.
        
        Returns:
            Dict with sync statistics
        """
        try:
            spreadsheet = self._get_spreadsheet()
            members_ws = spreadsheet.worksheet("Members")
            
            # Clear existing data (keep headers)
            members_ws.clear()
            members_ws.append_row(self.MEMBERS_HEADERS)
            
            # Get all members
            members = Member.objects.all().order_by('date_joined')
            
            # Prepare rows
            rows = []
            for order, member in enumerate(members, start=1):
                row = member_to_row(member, order=order)
                rows.append(row)
            
            # Batch update (Google Sheets API limit is 10000 cells per request)
            if rows:
                # Write in batches of 100 rows
                batch_size = 100
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    start_row = i + 2  # +2 because row 1 is headers
                    range_name = f'A{start_row}:S{start_row + len(batch) - 1}'
                    members_ws.update(range_name, batch)
            
            logger.info(f"Synced {len(rows)} members to Google Sheets")
            return {
                'success': True,
                'rows_synced': len(rows),
                'errors': []
            }
        except Exception as e:
            logger.error(f"Error syncing members to sheet: {e}")
            return {
                'success': False,
                'rows_synced': 0,
                'errors': [str(e)]
            }

    def sync_prospects_to_sheet(self) -> Dict[str, Any]:
        """
        Sync all Prospects from database to Google Sheets Prospects tab.
        
        Returns:
            Dict with sync statistics
        """
        try:
            spreadsheet = self._get_spreadsheet()
            prospects_ws = spreadsheet.worksheet("Prospects")
            
            # Clear existing data (keep headers)
            prospects_ws.clear()
            prospects_ws.append_row(self.PROSPECTS_HEADERS)
            
            # Get all prospects
            prospects = Prospect.objects.all().order_by('when_input')
            
            # Prepare rows
            rows = []
            for prospect in prospects:
                row = prospect_to_row(prospect)
                rows.append(row)
            
            # Batch update
            if rows:
                batch_size = 100
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    start_row = i + 2
                    range_name = f'A{start_row}:O{start_row + len(batch) - 1}'
                    prospects_ws.update(range_name, batch)
            
            logger.info(f"Synced {len(rows)} prospects to Google Sheets")
            return {
                'success': True,
                'rows_synced': len(rows),
                'errors': []
            }
        except Exception as e:
            logger.error(f"Error syncing prospects to sheet: {e}")
            return {
                'success': False,
                'rows_synced': 0,
                'errors': [str(e)]
            }

    def sync_event_to_sheet(self, event: Event) -> Dict[str, Any]:
        """
        Sync event registrations for a specific event to its tab.
        
        Args:
            event: Event instance
            
        Returns:
            Dict with sync statistics
        """
        try:
            worksheet = self.get_or_create_event_tab(event)
            
            # Clear existing data (keep headers)
            worksheet.clear()
            worksheet.append_row(self.MEMBERS_HEADERS)
            
            # Get registrations for this event
            registrations = EventRegistration.objects.filter(event=event).select_related('member')
            
            # Prepare rows
            rows = []
            for order, registration in enumerate(registrations, start=1):
                row = member_to_row(registration.member, order=order)
                rows.append(row)
            
            # Batch update
            if rows:
                batch_size = 100
                for i in range(0, len(rows), batch_size):
                    batch = rows[i:i + batch_size]
                    start_row = i + 2
                    range_name = f'A{start_row}:S{start_row + len(batch) - 1}'
                    worksheet.update(range_name, batch)
            
            logger.info(f"Synced {len(rows)} registrations for event {event.event_name} to Google Sheets")
            return {
                'success': True,
                'rows_synced': len(rows),
                'errors': []
            }
        except Exception as e:
            logger.error(f"Error syncing event to sheet: {e}")
            return {
                'success': False,
                'rows_synced': 0,
                'errors': [str(e)]
            }

    def sync_members_from_sheet(self) -> Dict[str, Any]:
        """
        Sync Members from Google Sheets to database.
        This is a read-only operation - we don't create members from sheet.
        Updates existing members if they exist.
        
        Returns:
            Dict with sync statistics
        """
        # For now, this is a placeholder
        # Full implementation would need to handle creating/updating Member records
        # which is complex due to ContactEmail/ContactPhone relationships
        logger.warning("sync_members_from_sheet is not fully implemented")
        return {
            'success': False,
            'rows_synced': 0,
            'errors': ['sync_members_from_sheet not fully implemented']
        }

    def sync_prospects_from_sheet(self) -> Dict[str, Any]:
        """
        Sync Prospects from Google Sheets to database.
        
        Returns:
            Dict with sync statistics
        """
        try:
            spreadsheet = self._get_spreadsheet()
            prospects_ws = spreadsheet.worksheet("Prospects")
            
            # Get all rows (skip header)
            all_values = prospects_ws.get_all_values()
            if len(all_values) < 2:
                return {
                    'success': True,
                    'rows_synced': 0,
                    'errors': []
                }
            
            headers = all_values[0]
            data_rows = all_values[1:]
            
            synced = 0
            errors = []
            
            for row_num, row in enumerate(data_rows, start=2):
                try:
                    # Pad row to match headers length
                    while len(row) < len(headers):
                        row.append("")
                    
                    prospect = row_to_prospect(row, headers)
                    if prospect:
                        # Update collision detection
                        update_prospect_collisions(prospect)
                        synced += 1
                except Exception as e:
                    error_msg = f"Row {row_num}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            logger.info(f"Synced {synced} prospects from Google Sheets")
            return {
                'success': True,
                'rows_synced': synced,
                'errors': errors
            }
        except Exception as e:
            logger.error(f"Error syncing prospects from sheet: {e}")
            return {
                'success': False,
                'rows_synced': 0,
                'errors': [str(e)]
            }

    def sync_event_from_sheet(self, event: Event) -> Dict[str, Any]:
        """
        Sync event registrations from Google Sheets to database.
        
        Args:
            event: Event instance
            
        Returns:
            Dict with sync statistics
        """
        # This would need to match sheet rows to members and create EventRegistration records
        # For now, placeholder
        logger.warning("sync_event_from_sheet is not fully implemented")
        return {
            'success': False,
            'rows_synced': 0,
            'errors': ['sync_event_from_sheet not fully implemented']
        }


# Singleton instance
_sync_service: Optional[MemberSyncService] = None


def get_sync_service() -> MemberSyncService:
    """Get or create the sync service instance."""
    global _sync_service
    if _sync_service is None:
        _sync_service = MemberSyncService()
    return _sync_service
