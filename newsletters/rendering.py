"""Markdown → safe HTML. Used for the web archive, previews and emails."""
import markdown
import nh3

ALLOWED_TAGS = {
    "p", "br", "hr", "h1", "h2", "h3", "h4", "strong", "em", "b", "i", "u", "s", "del",
    "ul", "ol", "li", "blockquote", "pre", "code", "a", "img",
    "table", "thead", "tbody", "tr", "th", "td",
}
ALLOWED_ATTRIBUTES = {
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "th": {"align"},
    "td": {"align"},
}
ALLOWED_URL_SCHEMES = {"http", "https", "mailto"}


def render_markdown(text: str) -> str:
    html = markdown.markdown(text or "", extensions=["extra", "sane_lists", "nl2br"], output_format="html")
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel="noopener noreferrer nofollow",
    )
