from __future__ import annotations

import copy
import unittest

from scripts.ci import validate_status_infrastructure as validator


class StatusInfrastructureValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = validator.load_template(validator.MAIN_TEMPLATE)

    def probe_statement(self, sid: str) -> dict:
        statements = self.template["Resources"]["ProbeFunction"]["Properties"]["Policies"][0]["Statement"]
        return next(statement for statement in statements if statement["Sid"] == sid)

    def test_rejects_wildcard_mixed_into_scoped_resource_list(self) -> None:
        statement = self.probe_statement("ExistingDatabaseRead")
        statement["Resource"] = [copy.deepcopy(statement["Resource"]), "*"]

        with self.assertRaisesRegex(AssertionError, "must not mix wildcard and scoped resources"):
            validator.validate_observability_and_iam(self.template)

    def test_rejects_extra_noncanonical_amplify_branch_resource(self) -> None:
        self.probe_statement("ExistingAmplifyRead")["Resource"].append(
            "arn:aws:amplify:us-west-2:111111111111:apps/unreviewed/branches/main"
        )

        with self.assertRaisesRegex(AssertionError, "canonical !Sub ARN entries only"):
            validator.validate_observability_and_iam(self.template)

    def test_rejects_extra_noncanonical_alarm_resource(self) -> None:
        self.probe_statement("StatusAlarmRead")["Resource"].append("*")

        with self.assertRaisesRegex(AssertionError, "canonical !Sub ARN entries only"):
            validator.validate_observability_and_iam(self.template)


if __name__ == "__main__":
    unittest.main()
