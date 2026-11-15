from pathlib import Path

from django.test import SimpleTestCase


class AmplifySingleWriterWorkflowTests(SimpleTestCase):
    def test_frontend_deploy_does_not_write_the_full_amplify_rule_list(self):
        repository_root = Path(__file__).resolve().parents[6]
        workflow = (repository_root / ".github/workflows/deploy-frontend.yml").read_text(encoding="utf-8")

        self.assertNotIn('"get-app"', workflow)
        self.assertNotIn('"update-app"', workflow)
        self.assertNotIn("aws amplify update-app", workflow)
        self.assertIn("aws amplify create-deployment", workflow)
        self.assertIn("aws amplify start-deployment", workflow)
