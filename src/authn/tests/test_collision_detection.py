"""
Unit tests for collision detection service.
"""

from django.test import TestCase
from ..models import Member, Prospect, ContactEmail, ContactPhone, MemberContactInfo
from ..services.collision_detection import (
    check_email_collision,
    check_phone_collision,
    update_prospect_collisions,
    normalize_phone,
)


class CollisionDetectionTest(TestCase):
    """Test collision detection functions."""
    
    def setUp(self):
        """Set up test data."""
        # Create a member with email and phone
        self.member = Member.objects.create_user(
            username='existing',
            email='existing@example.com',
            first_name='Existing',
            last_name='User',
            password='testpass123'
        )
        
        # Create contact email
        self.email = ContactEmail.objects.create(
            email_address='existing@example.com',
            email_type='primary',
            verified=True,
            subscribe=True
        )
        
        # Create contact phone
        self.phone = ContactPhone.objects.create(
            phone_number='1234567890',
            region='1-US',
            subscribe=True
        )
        
        # Create member contact info
        MemberContactInfo.objects.create(
            model_user=self.member,
            contact_email=self.email,
            contact_phone=self.phone
        )
    
    def test_check_email_collision_exists(self):
        """Test email collision detection when email exists."""
        self.assertTrue(check_email_collision('existing@example.com'))
        self.assertTrue(check_email_collision('EXISTING@EXAMPLE.COM'))  # Case insensitive
    
    def test_check_email_collision_not_exists(self):
        """Test email collision detection when email doesn't exist."""
        self.assertFalse(check_email_collision('new@example.com'))
        self.assertFalse(check_email_collision(''))
        self.assertFalse(check_email_collision(None))
    
    def test_check_phone_collision_exists(self):
        """Test phone collision detection when phone exists."""
        # Test various formats
        self.assertTrue(check_phone_collision('+11234567890'))
        self.assertTrue(check_phone_collision('1234567890'))
        self.assertTrue(check_phone_collision('+1 123 456 7890'))
    
    def test_check_phone_collision_not_exists(self):
        """Test phone collision detection when phone doesn't exist."""
        self.assertFalse(check_phone_collision('9876543210'))
        self.assertFalse(check_phone_collision(''))
        self.assertFalse(check_phone_collision(None))
    
    def test_normalize_phone(self):
        """Test phone number normalization."""
        self.assertEqual(normalize_phone('+1 (123) 456-7890'), '+11234567890')
        self.assertEqual(normalize_phone('1234567890'), '+1234567890')
        self.assertEqual(normalize_phone(''), '')
        self.assertEqual(normalize_phone(None), '')
    
    def test_update_prospect_collisions(self):
        """Test updating prospect collision fields."""
        # Create prospect with colliding email
        prospect = Prospect.objects.create(
            email='existing@example.com',  # Collides with member
            secondary_email='new@example.com',
            phone_number='1234567890',  # Collides with member
        )
        
        # Update collisions
        update_prospect_collisions(prospect)
        
        # Refresh from database
        prospect.refresh_from_db()
        
        self.assertTrue(prospect.primary_collision)
        self.assertFalse(prospect.secondary_collision)  # New email doesn't collide
        self.assertTrue(prospect.phone_collision)
    
    def test_update_prospect_collisions_no_collisions(self):
        """Test updating prospect collisions when no collisions exist."""
        prospect = Prospect.objects.create(
            email='new@example.com',
            secondary_email='new2@example.com',
            phone_number='9876543210',
        )
        
        update_prospect_collisions(prospect)
        
        prospect.refresh_from_db()
        
        self.assertFalse(prospect.primary_collision)
        self.assertFalse(prospect.secondary_collision)
        self.assertFalse(prospect.phone_collision)
