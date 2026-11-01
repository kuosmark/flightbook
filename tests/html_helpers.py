"""Read form controls and links using Python's standard HTML parser."""

from html.parser import HTMLParser


class Page(HTMLParser):
    """Collect rendered values, password inputs, and links for integration tests."""

    def __init__(self, response):
        super().__init__()
        self.values = {}
        self.passwords = {}
        self.links = []
        self.select_name = None
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs.get("href", ""))
        elif tag == "select":
            self.select_name = attrs.get("name")
        elif tag == "option" and "selected" in attrs and self.select_name:
            self.values[self.select_name] = attrs.get("value", "")
        elif tag == "input" and "name" in attrs:
            name = attrs["name"]
            value = attrs.get("value", "")
            if attrs.get("type") == "password":
                self.passwords[name] = value
            if attrs.get("type") not in ("radio", "checkbox") or "checked" in attrs:
                self.values[name] = value

    def handle_endtag(self, tag):
        if tag == "select":
            self.select_name = None


def csrf_token(response):
    """Require a successful form page containing a nonempty CSRF token."""
    assert response.status_code == 200, "The form page must be accessible"
    token = Page(response).values.get("csrf_token")
    assert token, "The form must render a nonempty CSRF token"
    return token
