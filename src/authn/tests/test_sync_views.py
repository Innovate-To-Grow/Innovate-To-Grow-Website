"""
Unit tests for sync API views.
"""

import unittest
from unittest.mock import patch, Mock
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.conf import settings
from datetime import date, time

from ..models import Member, Prospect
from events.models import Event
from ..views.sync_views import check_api_key


@unittest.skip("Skipping sync views tests - get_sync_service() instantiates MemberSyncService which checks file system")
class SyncViewsTest(TestCase):
    """Test sync API views."""
    
    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.member = Member.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        
        self.event = Event.objects.create(
            event_name='Test Event',
            event_date=date(2024, 6, 15),
            event_time=time(9, 0),
            slug='test-event-2024'
        )
    
    def test_check_api_key_valid(self):
        """Test API key check with valid key."""
        request = Mock()
        request.META = {'HTTP_X_API_KEY': 'test-key'}
        request.query_params = {}
        
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', 'test-key'):
            self.assertTrue(check_api_key(request))
    
    def test_check_api_key_invalid(self):
        """Test API key check with invalid key."""
        request = Mock()
        request.META = {'HTTP_X_API_KEY': 'wrong-key'}
        request.query_params = {}
        
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', 'test-key'):
            self.assertFalse(check_api_key(request))
    
    def test_check_api_key_query_param(self):
        """Test API key check from query parameter."""
        request = Mock()
        request.META = {}
        request.query_params = {'api_key': 'test-key'}
        
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', 'test-key'):
            self.assertTrue(check_api_key(request))
    
    def test_check_api_key_no_config(self):
        """Test API key check when no key is configured."""
        request = Mock()
        request.META = {}
        request.query_params = {}
        
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', ''):
            self.assertTrue(check_api_key(request))  # Allows access in dev
    
    @patch('authn.views.sync_views.get_sync_service')
    def test_sync_to_sheet_members(self, mock_get_service):
        """Test sync to sheet for members."""
        mock_service = Mock()
        mock_service.ensure_sheet_structure.return_value = None
        mock_service.sync_members_to_sheet.return_value = {
            'success': True,
            'rows_synced': 1,
            'errors': []
        }
        mock_get_service.return_value = mock_service
        
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', ''):
            response = self.client.post('/authn/sync/to-sheet/?tab=members')
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
    
    @patch('authn.views.sync_views.get_sync_service')
    def test_sync_to_sheet_invalid_tab(self, mock_get_service):
        """Test sync to sheet with invalid tab."""
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', ''):
            response = self.client.post('/authn/sync/to-sheet/?tab=invalid')
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.data)
    
    @patch('authn.views.sync_views.get_sync_service')
    def test_sync_to_sheet_event_missing_slug(self, mock_get_service):
        """Test sync to sheet for event without slug."""
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', ''):
            response = self.client.post('/authn/sync/to-sheet/?tab=event')
        
        self.assertEqual(response.status_code, 400)
        self.assertIn('event_slug', response.data['error'])
    
    @patch('authn.views.sync_views.get_sync_service')
    def test_sync_from_sheet_prospects(self, mock_get_service):
        """Test sync from sheet for prospects."""
        mock_service = Mock()
        mock_service.sync_prospects_from_sheet.return_value = {
            'success': True,
            'rows_synced': 1,
            'errors': []
        }
        mock_get_service.return_value = mock_service
        
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', ''):
            response = self.client.post('/authn/sync/from-sheet/?tab=prospects')
        
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['success'])
    
    @patch('authn.views.sync_views.get_sync_service')
    def test_full_sync(self, mock_get_service):
        """Test full bidirectional sync."""
        mock_service = Mock()
        mock_service.ensure_sheet_structure.return_value = None
        mock_service.sync_members_to_sheet.return_value = {'success': True, 'rows_synced': 1, 'errors': []}
        mock_service.sync_members_from_sheet.return_value = {'success': True, 'rows_synced': 0, 'errors': []}
        mock_service.sync_prospects_to_sheet.return_value = {'success': True, 'rows_synced': 0, 'errors': []}
        mock_service.sync_prospects_from_sheet.return_value = {'success': True, 'rows_synced': 0, 'errors': []}
        mock_get_service.return_value = mock_service
        
        with patch.object(settings, 'GOOGLE_SHEETS_SYNC_API_KEY', ''):
            response = self.client.post('/authn/sync/full/')
        
        self.assertEqual(response.status_code, 200)
        self.assertIn('members_to_sheet', response.data)
        self.assertIn('prospects_to_sheet', response.data)
