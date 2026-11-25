import tempfile
from pathlib import Path

from django.test import SimpleTestCase, TestCase, override_settings

from apps.core.static_cache import is_immutable_asset

INDEX_HTML = b'<!doctype html><html lang="ur" dir="rtl"><body><div id="root"></div></body></html>'


class SpaIndexTests(TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dist = Path(self._tmp.name)
        (self.dist / "index.html").write_bytes(INDEX_HTML)

    def tearDown(self):
        self._tmp.cleanup()

    def test_serves_index_for_client_routes(self):
        with override_settings(FRONTEND_DIST_DIR=self.dist):
            for path in ("/", "/worker/onboarding", "/some/deep/route?x=1"):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.content, INDEX_HTML)
                    self.assertIn("no-cache", response["Cache-Control"])

    def test_rejects_unsafe_methods(self):
        with override_settings(FRONTEND_DIST_DIR=self.dist):
            response = self.client.post("/")
        self.assertIn(response.status_code, (403, 405))

    def test_missing_build_gives_helpful_404(self):
        with override_settings(FRONTEND_DIST_DIR=self.dist / "missing"):
            response = self.client.get("/")
        self.assertEqual(response.status_code, 404)
        self.assertIn(b"Vite dev server", response.content)

    def test_admin_and_api_are_not_captured(self):
        with override_settings(FRONTEND_DIST_DIR=self.dist):
            self.assertEqual(self.client.get("/admin/").status_code, 302)
            self.assertEqual(self.client.get("/api/v1/health/live/").status_code, 200)


class ImmutableAssetTests(SimpleTestCase):
    def test_hashed_files_are_immutable(self):
        self.assertTrue(is_immutable_asset("", "/assets/index-BxYz12_3.js"))
        self.assertTrue(is_immutable_asset("", "/assets/noto-nastaliq-urdu-arabic-400-normal-Ab12Cd34.woff2"))
        self.assertTrue(is_immutable_asset("", "/static/admin/css/base.5af66c1b1797.css"))

    def test_unhashed_files_are_revalidated(self):
        self.assertFalse(is_immutable_asset("", "/index.html"))
        self.assertFalse(is_immutable_asset("", "/favicon.svg"))
        self.assertFalse(is_immutable_asset("", "/static/admin/css/base.css"))
        self.assertFalse(is_immutable_asset("", "/assets/logo.svg"))
