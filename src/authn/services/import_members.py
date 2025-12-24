"""
Service for importing members from Excel files.
"""
import secrets
import string
from dataclasses import dataclass
from typing import List, Tuple, Optional

from django.contrib.auth.models import Group
from django.db import transaction

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

from ..models import Member, MemberGroup


@dataclass
class ImportResult:
    """Result of a member import operation."""
    success: bool
    created_count: int = 0
    updated_count: int = 0
    skipped_count: int = 0
    errors: List[str] = None
    details: List[dict] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
        if self.details is None:
            self.details = []


def generate_random_password(length: int = 12) -> str:
    """Generate a random password."""
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def normalize_header(header: str) -> str:
    """Normalize column header to standard field name."""
    if not header:
        return ''
    
    header = str(header).strip().lower()
    
    # Map common variations to standard field names
    header_map = {
        # Username
        'username': 'username',
        'user': 'username',
        'user_name': 'username',
        # Email
        'email': 'email',
        'e-mail': 'email',
        'email_address': 'email',
        # First name
        'first_name': 'first_name',
        'firstname': 'first_name',
        'first name': 'first_name',
        # Middle name
        'middle_name': 'middle_name',
        'middlename': 'middle_name',
        'middle name': 'middle_name',
        # Last name
        'last_name': 'last_name',
        'lastname': 'last_name',
        'last name': 'last_name',
        # Full name (will be split)
        'name': 'full_name',
        'full_name': 'full_name',
        'fullname': 'full_name',
        'full name': 'full_name',
        # Groups
        'group': 'groups',
        'groups': 'groups',
        'role': 'groups',
        'roles': 'groups',
        # Is staff
        'is_staff': 'is_staff',
        'staff': 'is_staff',
        # Is active
        'is_active': 'is_active',
        'active': 'is_active',
        # Is active member
        'is_active_member': 'is_active_member',
        'active_member': 'is_active_member',
        'active member': 'is_active_member',
        # Organization
        'organization': 'organization',
        'company': 'organization',
        'org': 'organization',
        'organisation': 'organization',
    }
    
    return header_map.get(header, header)


def parse_boolean(value) -> bool:
    """Parse various boolean representations."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    
    str_val = str(value).strip().lower()
    return str_val in ('true', 'yes', '1', 'y', 'active')


def split_full_name(full_name: str) -> Tuple[str, str, str]:
    """Split full name into first, middle, last name."""
    if not full_name:
        return '', '', ''
    
    parts = full_name.strip().split()
    
    if len(parts) == 1:
        return parts[0], '', ''
    elif len(parts) == 2:
        return parts[0], '', parts[1]
    else:
        return parts[0], ' '.join(parts[1:-1]), parts[-1]


def import_members_from_excel(
    file,
    default_password: Optional[str] = None,
    update_existing: bool = False,
) -> ImportResult:
    """
    Import members from an Excel file.
    
    Expected columns (flexible naming):
    - username (required)
    - email (required)
    - first_name / name
    - middle_name
    - last_name
    - organization
    - groups (comma-separated)
    - is_staff
    - is_active
    - is_active_member
    
    Args:
        file: Uploaded Excel file
        default_password: Password to set for new users (generates random if None)
        update_existing: Whether to update existing users (by username or email)
    
    Returns:
        ImportResult with counts and any errors
    """
    if load_workbook is None:
        return ImportResult(
            success=False,
            errors=['openpyxl library not installed. Please run: pip install openpyxl']
        )
    
    result = ImportResult(success=True)
    
    try:
        # Load workbook
        wb = load_workbook(filename=file, read_only=True, data_only=True)
        ws = wb.active
        
        # Get headers from first row
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return ImportResult(success=False, errors=['Excel file is empty'])
        
        headers = [normalize_header(h) for h in rows[0]]
        
        # Validate required columns
        if 'username' not in headers and 'email' not in headers:
            return ImportResult(
                success=False,
                errors=['Excel file must contain a username or email column']
            )
        
        # Process data rows
        with transaction.atomic():
            for row_num, row in enumerate(rows[1:], start=2):
                if not any(row):  # Skip empty rows
                    continue
                
                row_data = dict(zip(headers, row))
                row_result = _process_member_row(
                    row_num, row_data, default_password, update_existing
                )
                
                if row_result['status'] == 'created':
                    result.created_count += 1
                elif row_result['status'] == 'updated':
                    result.updated_count += 1
                elif row_result['status'] == 'skipped':
                    result.skipped_count += 1
                
                if row_result.get('error'):
                    result.errors.append(f"Row {row_num}: {row_result['error']}")
                
                result.details.append(row_result)
        
        wb.close()
        
    except Exception as e:
        result.success = False
        result.errors.append(f'Error processing file: {str(e)}')
    
    return result


def _process_member_row(
    row_num: int,
    row_data: dict,
    default_password: Optional[str],
    update_existing: bool,
) -> dict:
    """Process a single row and create/update member."""
    result = {
        'row': row_num,
        'status': 'skipped',
        'username': None,
        'email': None,
        'error': None,
    }
    
    try:
        # Extract and clean data
        username = str(row_data.get('username', '')).strip() if row_data.get('username') else None
        email = str(row_data.get('email', '')).strip() if row_data.get('email') else None
        
        # Handle full_name if present
        if 'full_name' in row_data and row_data['full_name']:
            first, middle, last = split_full_name(str(row_data['full_name']))
            first_name = first
            middle_name = middle
            last_name = last
        else:
            first_name = str(row_data.get('first_name', '')).strip() if row_data.get('first_name') else ''
            middle_name = str(row_data.get('middle_name', '')).strip() if row_data.get('middle_name') else ''
            last_name = str(row_data.get('last_name', '')).strip() if row_data.get('last_name') else ''
        
        # Get organization
        organization = str(row_data.get('organization', '')).strip() if row_data.get('organization') else ''
        
        # Generate username from email if not provided
        if not username and email:
            username = email.split('@')[0]
        
        if not username:
            result['error'] = 'Missing username'
            return result
        
        result['username'] = username
        result['email'] = email
        
        # Check if user exists
        existing_member = None
        if Member.objects.filter(username=username).exists():
            existing_member = Member.objects.get(username=username)
        elif email and Member.objects.filter(email=email).exists():
            existing_member = Member.objects.get(email=email)
        
        if existing_member:
            if update_existing:
                # Update existing member
                if email:
                    existing_member.email = email
                if first_name:
                    existing_member.first_name = first_name
                if middle_name:
                    existing_member.middle_name = middle_name
                if last_name:
                    existing_member.last_name = last_name
                if organization:
                    existing_member.organization = organization
                
                # Update boolean fields if provided
                if 'is_active' in row_data:
                    existing_member.is_active = parse_boolean(row_data['is_active'])
                if 'is_active_member' in row_data:
                    existing_member.is_active_member = parse_boolean(row_data['is_active_member'])
                if 'is_staff' in row_data:
                    existing_member.is_staff = parse_boolean(row_data['is_staff'])
                
                existing_member.save()
                
                # Handle groups
                _update_member_groups(existing_member, row_data.get('groups'))
                
                result['status'] = 'updated'
            else:
                result['status'] = 'skipped'
                result['error'] = 'User already exists'
        else:
            # Create new member
            password = default_password or generate_random_password()
            
            member = Member.objects.create_user(
                username=username,
                email=email or '',
                password=password,
                first_name=first_name,
                middle_name=middle_name,
                last_name=last_name,
                organization=organization,
                is_active=parse_boolean(row_data.get('is_active', True)),
                is_active_member=parse_boolean(row_data.get('is_active_member', True)),
                is_staff=parse_boolean(row_data.get('is_staff', False)),
            )
            
            # Handle groups
            _update_member_groups(member, row_data.get('groups'))
            
            result['status'] = 'created'
            result['password'] = password if not default_password else None
    
    except Exception as e:
        result['error'] = str(e)
    
    return result


def _update_member_groups(member: Member, groups_str) -> None:
    """Update member's groups from comma-separated string."""
    if not groups_str:
        return
    
    group_names = [g.strip() for g in str(groups_str).split(',') if g.strip()]
    
    for group_name in group_names:
        # Check if it's a valid I2G group
        if group_name in MemberGroup.GROUP_CHOICES:
            group, _ = Group.objects.get_or_create(name=group_name)
            member.groups.add(group)
        else:
            # Try to find or create custom group
            group, _ = Group.objects.get_or_create(name=group_name)
            member.groups.add(group)


def generate_template_excel() -> bytes:
    """Generate a template Excel file for member import."""
    if load_workbook is None:
        raise ImportError('openpyxl library not installed')
    
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from io import BytesIO
    
    wb = Workbook()
    ws = wb.active
    ws.title = "Members"
    
    # Define headers
    headers = [
        ('username', 'Username (Required)', 20),
        ('email', 'Email (Required)', 30),
        ('first_name', 'First Name', 15),
        ('middle_name', 'Middle Name', 15),
        ('last_name', 'Last Name', 15),
        ('organization', 'Organization', 25),
        ('groups', 'Groups (comma-separated)', 30),
        ('is_active', 'Is Active', 12),
        ('is_active_member', 'Active Member', 14),
        ('is_staff', 'Is Staff', 12),
    ]
    
    # Style definitions
    header_font = Font(bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='4472C4', end_color='4472C4', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center')
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Write headers
    for col, (field, label, width) in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=label)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
        ws.column_dimensions[cell.column_letter].width = width
    
    # Add example row
    example_data = [
        'johndoe',
        'john.doe@example.com',
        'John',
        '',
        'Doe',
        'UC Merced',
        'Visitor - Attendee',
        'TRUE',
        'TRUE',
        'FALSE',
    ]
    
    for col, value in enumerate(example_data, 1):
        cell = ws.cell(row=2, column=col, value=value)
        cell.border = thin_border
    
    # Add instructions sheet
    ws_help = wb.create_sheet(title="Instructions")
    instructions = [
        ("Field Descriptions", ""),
        ("", ""),
        ("username", "Username, required field, used for login"),
        ("email", "Email address, required field"),
        ("first_name", "First name"),
        ("middle_name", "Middle name (if any)"),
        ("last_name", "Last name"),
        ("organization", "Organization or company name"),
        ("groups", "User groups, separate multiple groups with commas"),
        ("is_active", "Whether account is active (TRUE/FALSE)"),
        ("is_active_member", "Whether user is an active member (TRUE/FALSE)"),
        ("is_staff", "Whether user has staff permissions (TRUE/FALSE)"),
        ("", ""),
        ("Available Groups", ""),
        ("", "I2G Project Client - Mentor"),
        ("", "Judge"),
        ("", "Visitor - Attendee"),
        ("", "Family & Friends of I2G Student"),
        ("", "Student (NON-I2G)"),
        ("", "Faculty & Staff"),
    ]
    
    for row, (col1, col2) in enumerate(instructions, 1):
        ws_help.cell(row=row, column=1, value=col1)
        ws_help.cell(row=row, column=2, value=col2)
    
    ws_help.column_dimensions['A'].width = 20
    ws_help.column_dimensions['B'].width = 50
    
    # Save to bytes
    output = BytesIO()
    wb.save(output)
    output.seek(0)
    
    return output.getvalue()
