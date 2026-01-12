"""
Unit tests for Prospect model.
"""

from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from ..models import Prospect


class ProspectModelTest(TestCase):
    """Test Prospect model."""
    
    def test_create_prospect(self):
        """Test creating a prospect."""
        prospect = Prospect.objects.create(
            first_name='John',
            last_name='Doe',
            email='john@example.com',
            secondary_email='john.secondary@example.com',
            phone_number='1234567890',
            notes='Test prospect'
        )
        
        self.assertEqual(prospect.first_name, 'John')
        self.assertEqual(prospect.last_name, 'Doe')
        self.assertEqual(prospect.email, 'john@example.com')
        self.assertIsNotNone(prospect.when_input)
        self.assertIsNone(prospect.when_signed_up_as_member)
    
    def test_prospect_email_unique(self):
        """Test that email must be unique."""
        Prospect.objects.create(email='test@example.com')
        
        with self.assertRaises(Exception):  # IntegrityError
            Prospect.objects.create(email='test@example.com')
    
    def test_prospect_optional_fields(self):
        """Test that optional fields can be None."""
        prospect = Prospect.objects.create(
            email='minimal@example.com'
        )
        
        self.assertIsNone(prospect.first_name)
        self.assertIsNone(prospect.last_name)
        self.assertIsNone(prospect.secondary_email)
        self.assertIsNone(prospect.phone_number)
    
    def test_prospect_str(self):
        """Test Prospect string representation."""
        prospect = Prospect.objects.create(
            first_name='Jane',
            last_name='Smith',
            email='jane@example.com'
        )
        
        self.assertIn('Jane', str(prospect))
        self.assertIn('jane@example.com', str(prospect))
    
    def test_prospect_str_no_name(self):
        """Test Prospect string representation with no name."""
        prospect = Prospect.objects.create(
            email='noname@example.com'
        )
        
        self.assertIn('Unknown', str(prospect))
        self.assertIn('noname@example.com', str(prospect))
    
    def test_mark_as_member(self):
        """Test marking prospect as member."""
        prospect = Prospect.objects.create(
            email='test@example.com'
        )
        
        self.assertIsNone(prospect.when_signed_up_as_member)
        
        prospect.mark_as_member()
        prospect.refresh_from_db()
        
        self.assertIsNotNone(prospect.when_signed_up_as_member)
        
        # Mark again - should not change
        original_time = prospect.when_signed_up_as_member
        prospect.mark_as_member()
        prospect.refresh_from_db()
        
        self.assertEqual(prospect.when_signed_up_as_member, original_time)
    
    def test_prospect_defaults(self):
        """Test default values for prospect fields."""
        prospect = Prospect.objects.create(
            email='defaults@example.com'
        )
        
        self.assertFalse(prospect.primary_collision)
        self.assertFalse(prospect.secondary_collision)
        self.assertFalse(prospect.phone_collision)
        self.assertEqual(prospect.notes, '')
