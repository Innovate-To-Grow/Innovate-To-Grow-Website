import unittest

from scripts.ci.summarize_workflow_jobs import render_markdown


class SummarizeWorkflowJobs(unittest.TestCase):
    def test_renders_jobs_sorted_by_duration(self):
        markdown = render_markdown(
            {
                "jobs": [
                    {
                        "name": "Short",
                        "conclusion": "success",
                        "started_at": "2026-06-06T01:00:00Z",
                        "completed_at": "2026-06-06T01:00:10Z",
                    },
                    {
                        "name": "Long",
                        "conclusion": "success",
                        "started_at": "2026-06-06T01:00:00Z",
                        "completed_at": "2026-06-06T01:02:05Z",
                        "html_url": "https://example.test/job",
                    },
                ]
            }
        )

        self.assertIn("## CI Timing Report", markdown)
        self.assertLess(markdown.index("Long"), markdown.index("Short"))
        self.assertIn("2m 5s", markdown)
        self.assertIn("[Long](https://example.test/job)", markdown)

    def test_handles_empty_payload(self):
        markdown = render_markdown({"jobs": []})

        self.assertIn("No jobs found", markdown)


if __name__ == "__main__":
    unittest.main()
