"""
Capture all rendered HTML pages from the old Flask site.
Saves each page as a standalone HTML file.
"""
import os
import urllib.request
import urllib.error

BASE_URL = "http://localhost:5050"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captured_pages")

ROUTES = [
    ("/", "home-post-event"),
    ("/about", "about"),
    ("/privacy", "terms_and_conditions"),
    ("/engineering-capstone", "engineering-capstone"),
    ("/about_EngSL", "about_EngSL"),
    ("/software-capstone", "software-capstone"),
    ("/event", "event"),
    ("/schedule", "schedule"),
    ("/projects-teams", "projects-teams"),
    ("/judges", "judges"),
    ("/attendees", "attendees"),
    ("/students", "students"),
    ("/acknowledgement", "acknowledgement"),
    ("/past-events", "past-events"),
    ("/projects", "projects"),
    ("/current-projects", "current-projects"),
    ("/project-submission", "project-submission"),
    ("/sample-proposals", "sample-proposals"),
    ("/partnership", "partnership"),
    ("/sponsorship", "sponsorship"),
    ("/FAQs", "faq"),
    ("/I2G-student-agreement", "I2G-student-agreement"),
    ("/ferpa", "ferpa"),
    ("/i2g-students-preparation", "i2g-students-preparation"),
    ("/video-preparation", "video-preparation"),
    ("/capstone-purchasing-reimbursement", "capstone-purchasing-reimbursement"),
    ("/contact-us", "contact-us"),
    ("/judging", "judging"),
    ("/template", "template"),
    ("/template-email-team-students", "template-email-team-students"),
    ("/I2G-project-sponsor-acknowledgement", "I2G-project-sponsor-acknowledgement"),
    ("/home-during-event", "home-during-event"),
    ("/home-post-event", "home-post-event"),
    ("/2025-fall-event", "2025-fall-event"),
    ("/2025-spring-event", "2025-spring-event"),
    ("/2024-fall-event", "2024-fall-event"),
    ("/2024-spring-event", "2024-spring-event"),
    ("/2023-fall-event", "2023-fall-event"),
    ("/2023-spring-event", "2023-spring-event"),
    ("/2022-fall-event", "2022-fall-event"),
    ("/2022-spring-event", "2022-spring-event"),
    ("/2021-fall-event", "2021-fall-event"),
    ("/2021-spring-event", "2021-spring-event"),
    ("/2020-fall-post-event", "2020-fall-post-event"),
    ("/2014-sponsors", "2014-sponsors"),
    ("/2015-sponsors", "2015-sponsors"),
    ("/past-projects", "past-projects"),
]

os.makedirs(OUTPUT_DIR, exist_ok=True)

success = 0
failed = 0

for path, name in ROUTES:
    url = f"{BASE_URL}{path}"
    filename = f"{name}.html"
    filepath = os.path.join(OUTPUT_DIR, filename)
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as response:
            html = response.read().decode("utf-8")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html)
            size = len(html)
            print(f"OK  {path:50s} -> {filename} ({size:,} bytes)")
            success += 1
    except urllib.error.HTTPError as e:
        print(f"ERR {path:50s} -> HTTP {e.code}")
        failed += 1
    except Exception as e:
        print(f"ERR {path:50s} -> {e}")
        failed += 1

print(f"\nDone: {success} captured, {failed} failed")
