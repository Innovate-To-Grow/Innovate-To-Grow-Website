from django.urls import reverse

from apps.core.tests.admin.navigation.test_admin_index_navigation import _AdminIndexNavigationCase


class AdminIndexNavigationTest(_AdminIndexNavigationCase):
    def test_cli_admin_pages_render_as_admin_tabs(self):
        for url, active_href in (
            (reverse("admin:cli_admin_cliaccesstoken_changelist"), "/admin/cli_admin/cliaccesstoken/"),
            (
                reverse("admin:cli_admin_cliauthorizationcode_changelist"),
                "/admin/cli_admin/cliauthorizationcode/",
            ),
            (reverse("admin:cli_admin_cliauditlog_changelist"), "/admin/cli_admin/cliauditlog/"),
        ):
            with self.subTest(url=url):
                response = self.client.get(url)

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'id="tabs-items"')
                self.assertContains(response, 'href="/admin/cli_admin/cliaccesstoken/"')
                self.assertContains(response, 'href="/admin/cli_admin/cliauthorizationcode/"')
                self.assertContains(response, 'href="/admin/cli_admin/cliauditlog/"')
                self.assertContains(response, f'href="{active_href}" class="active"')

        response = self.client.get(reverse("admin:cli_admin_cliaccesstoken_changelist"))
        html = response.content.decode()
        sidebar_html = html.split('<div id="main"', maxsplit=1)[0]
        self.assertNotIn("Authorization Codes", sidebar_html)
        self.assertNotIn("Audit Log", sidebar_html)
