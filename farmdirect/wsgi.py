"""WSGI middleware: mount the whole Flask app under a URL prefix.

Used only when the environment variable FD_URL_PREFIX is set (sandbox preview
proxy). Standalone usage (hackathon demo) runs without a prefix.

Two incoming shapes are supported:
  - "/prefix/..."  (direct request, e.g. `flask run` behind a plain proxy)
  - "/..."         (prefix already stripped by the Next.js rewrite proxy)
In both cases SCRIPT_NAME is set so `url_for` always generates
prefix-correct URLs for links, static files, redirects and fetch() calls.
"""


class PrefixMiddleware:
    def __init__(self, wsgi_app, prefix=""):
        self.wsgi_app = wsgi_app
        self.prefix = prefix.rstrip("/")

    def __call__(self, environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path == self.prefix:
            path = "/"
        elif path.startswith(self.prefix + "/"):
            path = path[len(self.prefix):]
        # else: request already arrived without the prefix — keep as-is.
        environ["PATH_INFO"] = path
        environ["SCRIPT_NAME"] = self.prefix
        return self.wsgi_app(environ, start_response)
