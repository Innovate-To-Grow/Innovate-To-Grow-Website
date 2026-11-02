"""Per-member project throttles. Each rate is a request-limit policy (``policy_scope``), read live on every request,
so staff edit it in the admin without a restart (``apps.core.services.request_limits.view_limits``)."""

from apps.core.services.request_limits.view_limits import MemberRateThrottle


class PastProjectShareRateThrottle(MemberRateThrottle):
    # Creating a share requires authentication, so throttle per member (not per anonymous IP).
    scope = "past_project_share"
    policy_scope = "view-past-project-share"


class PastProjectShareUpdateRateThrottle(MemberRateThrottle):
    # Changing or deleting a share (each edit of a shared list is one PATCH), per owner.
    scope = "past_project_share_update"
    policy_scope = "view-past-project-share-update"


class PastProjectAISearchRateThrottle(MemberRateThrottle):
    # AI search requires authentication, so throttle per member.
    scope = "past_project_ai_search"
    policy_scope = "view-ai-search"
