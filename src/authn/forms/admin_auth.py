from django.contrib.admin.forms import AdminAuthenticationForm
from django.utils.translation import gettext_lazy as _


class EmailAdminAuthenticationForm(AdminAuthenticationForm):
    """
    Admin login form with an email label/placeholder.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        field = self.fields.get("username")
        if field:
            field.label = _("Email")
            field.widget.attrs.setdefault("placeholder", _("Email"))
