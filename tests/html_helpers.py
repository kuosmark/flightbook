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
        self.form_action = None
        self.csrf_tokens = {}
        self.feed(response.get_data(as_text=True))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self.form_action = attrs.get("action", "")
        elif tag == "a":
            self.links.append(attrs.get("href", ""))
        elif tag == "select":
            self.select_name = attrs.get("name")
        elif tag == "option" and "selected" in attrs and self.select_name:
            self.values[self.select_name] = attrs.get("value", "")
        elif tag == "input" and "name" in attrs:
            name = attrs["name"]
            value = attrs.get("value", "")
            if name == "csrf_token" and self.form_action is not None:
                self.csrf_tokens.setdefault(self.form_action, []).append(value)
            if attrs.get("type") == "password":
                self.passwords[name] = value
            if attrs.get("type") not in ("radio", "checkbox") or "checked" in attrs:
                self.values[name] = value

    def handle_endtag(self, tag):
        if tag == "select":
            self.select_name = None
        elif tag == "form":
            self.form_action = None


def csrf_token(response, action=""):
    """Read one token from the target form; an empty action posts to the current URL."""
    assert response.status_code == 200, "The form page must be accessible"
    tokens = Page(response).csrf_tokens.get(action, [])
    assert len(tokens) == 1 and tokens[0], "The target form must render exactly one CSRF token"
    return tokens[0]
