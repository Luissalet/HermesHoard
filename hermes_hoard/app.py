import os
from pathlib import Path
from .native import SPECS, factory
from .runtime import create_runtime


def create_app(data_dir=None, port=None):
    port = port or int(os.environ.get("HERMES_PORT", "5221"))
    root = Path(__file__).parent
    data_dir = Path(data_dir or os.environ.get("HERMES_DATA_DIR") or root.parent / "data")
    runtime = create_runtime(name="Hermes's Hoard", product="hermes", root=root, data_dir=data_dir,
                             specs=SPECS, port=port, factory=lambda key, path: factory(key, path, port=port))
    return CartDoor(runtime)


CART_PREFIX = "/products/api/cart/x/"
_BROWSER_HEADERS = (b"origin", b"sec-fetch-site", b"sec-fetch-mode", b"sec-fetch-dest")


class CartDoor:
    """The cart-runner extension calls from the user's browser, on its own origin. Its routes are opened by a key
    (``X-Hermes-Cart-Key``, checked by the route), not by where the call comes from: for those paths, and only when the
    key header is there, the origin headers are left out so the origin rules behind do not turn the extension away."""

    def __init__(self, app):
        self.app = app

    def __getattr__(self, name):
        return getattr(self.app, name)

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http" and scope.get("path", "").startswith(CART_PREFIX):
            headers = scope.get("headers") or []
            if any(k == b"x-hermes-cart-key" and v for k, v in headers):
                scope = dict(scope, headers=[(k, v) for k, v in headers if k not in _BROWSER_HEADERS])
        await self.app(scope, receive, send)
