from bs4 import BeautifulSoup


def html_has_hidden_content(html: str) -> bool:
    return bool(html_hidden_reasons(html))


def html_hidden_reasons(html: str) -> list[str]:
    reasons = []
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(style=True):
        compact = tag.get("style", "").lower().replace(" ", "")
        if "display:none" in compact or "visibility:hidden" in compact:
            reasons.append("HTML contains hidden elements (display:none / visibility:hidden)")
        if "font-size:0" in compact:
            reasons.append("HTML contains zero-size text (font-size:0)")
    return reasons
