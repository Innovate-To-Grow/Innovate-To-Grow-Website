from django.db import models


class SiteSettings(models.Model):
    """Singleton model for site-wide settings like homepage selection.

    This intentionally extends plain models.Model instead of ProjectControlModel.
    The pk=1 singleton pattern (enforced in save()) is incompatible with UUID
    primary keys, soft-delete, and versioning provided by ProjectControlModel.
    A single-row settings table does not need those features.
    """

    homepage_page = models.ForeignKey(
        "pages.CMSPage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text='Published CMS page to render at "/". Leave blank to use the published "/" page.',
    )

    class Meta:
        verbose_name = "Site Settings"
        verbose_name_plural = "Site Settings"

    def __str__(self):
        return "Site Settings"

    def save(self, *args, **kwargs):
        # Enforce singleton: always use pk=1
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def get_homepage_route(self):
        from pages.models import CMSPage

        if self.homepage_page_id:
            selected_page = CMSPage.all_objects.filter(pk=self.homepage_page_id).first()
            if selected_page and not selected_page.is_deleted and selected_page.status == "published":
                return selected_page.route

        root_page = CMSPage.objects.filter(route="/", status="published").first()
        if root_page:
            return root_page.route

        return "/"
