from ..helpers import _serialize_rows


def search_cms_pages(params):
    from cms.models import CMSPage

    qs = CMSPage.objects.all()
    if params.get("title"):
        qs = qs.filter(title__icontains=params["title"])
    if params.get("slug"):
        qs = qs.filter(slug__icontains=params["slug"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    return _serialize_rows(
        qs.order_by("sort_order"),
        [
            "id",
            "title",
            "slug",
            "route",
            "status",
            "meta_description",
            "published_at",
        ],
    )
