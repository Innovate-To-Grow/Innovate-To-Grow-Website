from apps.core.admin.request_limits.cards import smart_line
from apps.core.services.request_limits.reporting import overview as overview_module
from apps.core.tests.admin.request_limits.test_status import CUT_AT

from .helpers import RequestLimitsAdminTestCase


class SmartLineTests(RequestLimitsAdminTestCase):
    def test_a_cut_without_reasons_names_the_pressure(self):
        view = overview_module.overview()["scopes"]["ai"]
        decision = {"action": "shed", "pressure": "overload", "reasons": [], "at": CUT_AT.isoformat()}
        changed = overview_module.ScopeView(**{**view.__dict__, "factor": 0.5, "decision": decision})
        self.assertEqual(smart_line(changed), "Smart ×0.50 of the baseline: cut at 07:55:00 UTC because of overload.")
