"""
Admin forms for authn app.
"""
from django import forms


class MemberImportForm(forms.Form):
    """Form for importing members from Excel file."""
    
    excel_file = forms.FileField(
        label='Excel File',
        help_text='Upload a .xlsx or .xls format Excel file',
        widget=forms.FileInput(attrs={
            'accept': '.xlsx,.xls',
            'class': 'vTextField',
        })
    )
    
    set_password = forms.CharField(
        label='Default Password',
        required=False,
        help_text='Set a default password for imported users (leave empty to generate random passwords)',
        widget=forms.PasswordInput(attrs={
            'class': 'vTextField',
            'autocomplete': 'new-password',
        })
    )
    
    send_welcome_email = forms.BooleanField(
        label='Send Welcome Email',
        required=False,
        initial=False,
        help_text='Send welcome email to users after import (requires email service configuration)',
    )
    
    def clean_excel_file(self):
        """Validate the uploaded file."""
        file = self.cleaned_data.get('excel_file')
        if file:
            # Check file extension
            if not file.name.endswith(('.xlsx', '.xls')):
                raise forms.ValidationError('Please upload a .xlsx or .xls format file')
            
            # Check file size (max 5MB)
            if file.size > 5 * 1024 * 1024:
                raise forms.ValidationError('File size cannot exceed 5MB')
        
        return file
