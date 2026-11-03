"""The Microsoft Graph access check in the admin: the "Run access check" page of a Graph config (Core app), and
the read-only list of recorded runs (``MicrosoftGraphAccessCheck``) that the go-live gate reads as evidence.

Production has no ECS Exec, so this page is how the check runs there (``manage.py verify_graph_access`` does the
same from a shell). A run requests a fresh token and makes real Graph requests, probe emails to the I2G mailbox
included, so it is a POST behind a confirmation page and redirects to the recorded result.
"""

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils.html import format_html, format_html_join
from unfold.decorators import display

from apps.core.models import MicrosoftGraphAccessCheck
from apps.core.services.email.graph.access_check import precondition_problem, run_and_record
from apps.core.services.email.graph.credential.expiry import local_time_text

from ..common.base import ReadOnlyModelAdmin
from .microsoft_graph_panel import ACCESS_CHECK_URL_NAME, EVIDENCE_URL_NAME, URL_NAME_PREFIX, certificate_card

Verdict = MicrosoftGraphAccessCheck.Verdict
CORE_APP_ONLY = "Running the Microsoft Graph access check needs the Core app."
VERDICT_LEVELS = {Verdict.COMPLIANT: messages.SUCCESS, Verdict.INCOMPLETE: messages.WARNING}
VERDICT_LABELS = {Verdict.COMPLIANT: "success", Verdict.INCOMPLETE: "warning", Verdict.NOT_COMPLIANT: "danger"}
RESULT_COLUMNS = ("Outcome", "Check", "Mailbox", "Expected", "Status", "Graph code", "Request ID", "Note")


class GraphAccessCheckViewMixin:
    """The "Run access check" page for ``MicrosoftGraphProviderConfigAdmin`` (with ``GraphCertificateViewsMixin``)."""

    def get_access_check_urls(self):
        view = self.admin_site.admin_view(self.run_access_check_view)
        return [path("<path:object_id>/access-check/", view, name=ACCESS_CHECK_URL_NAME)]

    def run_access_check_view(self, request, object_id):
        if not self.has_change_permission(request):
            raise PermissionDenied(CORE_APP_ONLY)
        config = self._config(request, object_id)
        problem = precondition_problem(config, config.access_check_deny_mailbox)
        change_url = reverse(f"admin:{URL_NAME_PREFIX}_change", args=[config.pk])
        if request.method != "POST":
            context = {
                **self.admin_site.each_context(request),
                "title": "Run the Microsoft Graph access check",
                "opts": self.opts,
                "original": config,
                "problem": problem,
                "current": certificate_card(config.current_certificate),
                "scopes": list(config.mailbox_scopes.all()),
                "cancel_url": change_url,
            }
            return TemplateResponse(request, "admin/core/microsoftgraphproviderconfig/run_access_check.html", context)
        if problem:
            messages.error(request, problem)
            return HttpResponseRedirect(change_url)
        report, check = run_and_record(
            config,
            deny_mailbox=config.access_check_deny_mailbox,
            source=MicrosoftGraphAccessCheck.Source.ADMIN,
            run_by=request.user,
        )
        level = VERDICT_LEVELS.get(check.verdict, messages.ERROR)
        messages.add_message(request, level, f"{report.summary()}. {report.conclusion()}")
        return HttpResponseRedirect(reverse(f"admin:{EVIDENCE_URL_NAME}", args=[check.pk]))


@admin.register(MicrosoftGraphAccessCheck)
class MicrosoftGraphAccessCheckAdmin(ReadOnlyModelAdmin):
    """Recorded access checks: evidence for InfoSec and the go-live gate. Nothing here can be edited or deleted."""

    list_display = (
        "checked_at",
        "verdict_badge",
        "config",
        "certificate_sha1",
        "deny_mailbox",
        "mailbox_restriction_passed",
        "roles_within_approval",
        "source",
        "run_by",
    )
    list_filter = ("verdict", "source")
    search_fields = ("certificate_sha1", "deny_mailbox")
    ordering = ("-created_at",)
    fieldsets = (
        (None, {"fields": ("verdict_badge", "checked_at", "config", "source", "run_by")}),
        ("Checked", {"fields": ("tenant_id", "client_id", "certificate", "certificate_sha1", "deny_mailbox")}),
        (
            "Findings",
            {
                "fields": (
                    "mailbox_restriction_passed",
                    "complete",
                    "granted_roles_text",
                    "approved_roles_text",
                    "roles_within_approval",
                    "permission_exception_reference",
                    "results_table",
                ),
            },
        ),
    )
    readonly_fields = tuple(name for _title, options in fieldsets for name in options["fields"])

    @display(description="Verdict", label=True)
    def verdict_badge(self, obj):
        return obj.get_verdict_display(), VERDICT_LABELS.get(obj.verdict, "danger")

    @display(description="Checked", ordering="created_at")
    def checked_at(self, obj):
        return local_time_text(obj.created_at)

    @display(description="Granted application roles")
    def granted_roles_text(self, obj):
        if obj.granted_roles is None:
            return "Could not be read"
        return ", ".join(obj.granted_roles) or "None in the token (RBAC for Applications grants never appear there)"

    @display(description="Approved application roles (at the time)")
    def approved_roles_text(self, obj):
        return ", ".join(obj.approved_roles)

    @display(description="Probe results")
    def results_table(self, obj):
        rows = format_html_join(
            "",
            "<tr>" + "<td class='px-2 py-1 align-top'>{}</td>" * len(RESULT_COLUMNS) + "</tr>",
            (_result_cells(result) for result in obj.results if isinstance(result, dict)),
        )
        header = format_html_join("", "<th class='px-2 py-1 text-left'>{}</th>", ((name,) for name in RESULT_COLUMNS))
        return format_html("<table class='text-xs'><thead><tr>{}</tr></thead><tbody>{}</tbody></table>", header, rows)


def _result_cells(result: dict) -> tuple:
    status = result.get("status")
    names = ("outcome", "check", "mailbox", "expected")
    return (
        *(result.get(name, "") for name in names),
        "-" if status is None else status,
        *(result.get(name, "") for name in ("code", "request_id", "note")),
    )
