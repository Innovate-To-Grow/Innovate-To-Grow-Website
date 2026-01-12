"""
Unit tests for member/prospect serialization functions.
"""

from django.test import TestCase
from django.utils import timezone
from datetime import datetime

from ..models import Member, Prospect, ContactEmail, ContactPhone, MemberContactInfo
from ..services.member_serialization import (
    member_to_row,
    prospect_to_row,
    row_to_prospect,
    format_datetime,
    parse_datetime,
    bool_to_sheet,
    sheet_to_bool,
)


class MemberSerializationTest(TestCase):
    """Test member serialization functions."""
    
    def setUp(self):
        """Set up test data."""
        self.member = Member.objects.create_user(
            username='testuser',
            email='test@example.com',
            first_name='John',
            last_name='Doe',
            password='testpass123'
        )
    
    def test_member_to_row_basic(self):
        """Test member_to_row with basic member."""
        row = member_to_row(self.member, order=1)
        
        self.assertEqual(len(row), 19)
        self.assertEqual(row[0], '1')  # Order
        self.assertEqual(row[1], 'John')  # First Name
        self.assertEqual(row[2], 'Doe')  # Last Name
        self.assertIn('202', row[3])  # When Started (contains year)
    
    def test_member_to_row_with_contact_info(self):
        """Test member_to_row with contact email and phone."""
        # Create contact email
        email = ContactEmail.objects.create(
            email_address='primary@example.com',
            email_type='primary',
            verified=True,
            subscribe=True
        )
        
        # Create contact phone
        phone = ContactPhone.objects.create(
            phone_number='1234567890',
            region='1-US',
            subscribe=True
        )
        
        # Create member contact info
        MemberContactInfo.objects.create(
            model_user=self.member,
            contact_email=email,
            contact_phone=phone
        )
        
        row = member_to_row(self.member, order=1)
        
        self.assertEqual(row[5], 'primary@example.com')  # Primary Email
        self.assertEqual(row[6], 'Yes')  # Primary Verified
        self.assertEqual(row[7], 'Yes')  # Primary Subscribed
        self.assertIn('+1', row[15])  # Phone Number
    
    def test_format_datetime(self):
        """Test datetime formatting."""
        dt = timezone.now()
        formatted = format_datetime(dt)
        self.assertIsInstance(formatted, str)
        self.assertIn('202', formatted)  # Contains year
    
    def test_format_datetime_none(self):
        """Test datetime formatting with None."""
        self.assertEqual(format_datetime(None), '')
    
    def test_parse_datetime(self):
        """Test datetime parsing."""
        date_str = '2024-01-15 2:30 PM'
        dt = parse_datetime(date_str)
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2024)
        self.assertEqual(dt.month, 1)
        self.assertEqual(dt.day, 15)
    
    def test_parse_datetime_empty(self):
        """Test datetime parsing with empty string."""
        self.assertIsNone(parse_datetime(''))
        self.assertIsNone(parse_datetime(None))
    
    def test_bool_to_sheet(self):
        """Test boolean to sheet conversion."""
        self.assertEqual(bool_to_sheet(True), 'Yes')
        self.assertEqual(bool_to_sheet(False), 'No')
        self.assertEqual(bool_to_sheet(None), '')
    
    def test_sheet_to_bool(self):
        """Test sheet value to boolean conversion."""
        self.assertTrue(sheet_to_bool('Yes'))
        self.assertTrue(sheet_to_bool('yes'))
        self.assertTrue(sheet_to_bool('True'))
        self.assertTrue(sheet_to_bool('1'))
        self.assertFalse(sheet_to_bool('No'))
        self.assertFalse(sheet_to_bool('no'))
        self.assertFalse(sheet_to_bool('False'))
        self.assertFalse(sheet_to_bool('0'))


class ProspectSerializationTest(TestCase):
    """Test prospect serialization functions."""
    
    def setUp(self):
        """Set up test data."""
        self.prospect = Prospect.objects.create(
            first_name='Jane',
            last_name='Smith',
            email='jane@example.com',
            secondary_email='jane.secondary@example.com',
            phone_number='9876543210',
            notes='Test prospect'
        )
    
    def test_prospect_to_row(self):
        """Test prospect_to_row."""
        row = prospect_to_row(self.prospect)
        
        self.assertEqual(len(row), 15)
        self.assertEqual(row[0], 'Jane')  # First Name
        self.assertEqual(row[1], 'Smith')  # Last Name
        self.assertEqual(row[2], 'jane@example.com')  # Email
        self.assertEqual(row[8], 'jane.secondary@example.com')  # Secondary Email
        self.assertEqual(row[11], '9876543210')  # Phone Number
        self.assertEqual(row[14], 'Test prospect')  # Notes
    
    def test_row_to_prospect(self):
        """Test row_to_prospect."""
        headers = [
            'First Name (optional)',
            'Last Name (optional)',
            'Email',
            'When Input?',
            'When signed up as member?',
            'When last checked?',
            'Bounced (when)?',
            'Collision?',
            'Secondary Email (optional)',
            'Secondary Bounced (when)?',
            'Secondary Collision',
            'Phone Number (optional)',
            'Phone Bounced (when)?',
            'Phone Collision',
            'Notes',
        ]
        
        row = [
            'New',
            'Prospect',
            'new@example.com',
            '2024-01-15 2:30 PM',
            '',
            '2024-01-15 2:30 PM',
            '',
            'No',
            '',
            '',
            'No',
            '',
            '',
            'No',
            'New prospect notes',
        ]
        
        prospect = row_to_prospect(row, headers)
        
        self.assertIsNotNone(prospect)
        self.assertEqual(prospect.email, 'new@example.com')
        self.assertEqual(prospect.first_name, 'New')
        self.assertEqual(prospect.last_name, 'Prospect')
        self.assertEqual(prospect.notes, 'New prospect notes')
        self.assertFalse(prospect.primary_collision)
    
    def test_row_to_prospect_update_existing(self):
        """Test row_to_prospect updates existing prospect."""
        headers = [
            'First Name (optional)',
            'Last Name (optional)',
            'Email',
            'When Input?',
            'When signed up as member?',
            'When last checked?',
            'Bounced (when)?',
            'Collision?',
            'Secondary Email (optional)',
            'Secondary Bounced (when)?',
            'Secondary Collision',
            'Phone Number (optional)',
            'Phone Bounced (when)?',
            'Phone Collision',
            'Notes',
        ]
        
        row = [
            'Jane',
            'Smith Updated',
            'jane@example.com',  # Existing email
            '2024-01-15 2:30 PM',
            '',
            '2024-01-15 2:30 PM',
            '',
            'No',
            '',
            '',
            'No',
            '',
            '',
            'No',
            'Updated notes',
        ]
        
        prospect = row_to_prospect(row, headers)
        
        self.assertEqual(prospect.id, self.prospect.id)  # Same prospect
        self.assertEqual(prospect.last_name, 'Smith Updated')
        self.assertEqual(prospect.notes, 'Updated notes')
