"""Tests for the is_link_only URL classifier."""

import unittest

from app.service import is_link_only


class IsLinkOnlyTests(unittest.TestCase):
    """Verify the URL-only classifier used for note/link routing."""

    def test_bare_http_url(self) -> None:
        self.assertTrue(is_link_only("http://example.com"))

    def test_bare_https_url(self) -> None:
        self.assertTrue(is_link_only("https://youtube.com/watch?v=abc123"))

    def test_url_with_trailing_whitespace(self) -> None:
        self.assertTrue(is_link_only("https://example.com   "))

    def test_url_with_trailing_newline(self) -> None:
        self.assertTrue(is_link_only("https://example.com\n"))

    def test_url_with_leading_whitespace(self) -> None:
        self.assertTrue(is_link_only("  https://example.com"))

    def test_url_with_query_params(self) -> None:
        self.assertTrue(is_link_only("https://docs.google.com/doc?id=123&mode=edit"))

    def test_url_with_fragment(self) -> None:
        self.assertTrue(is_link_only("https://example.com/page#section"))

    def test_url_with_path(self) -> None:
        self.assertTrue(is_link_only("https://github.com/user/repo/issues/42"))

    def test_url_plus_text_after(self) -> None:
        self.assertFalse(is_link_only("https://example.com check this"))

    def test_text_plus_url(self) -> None:
        self.assertFalse(is_link_only("check this https://example.com"))

    def test_two_urls(self) -> None:
        self.assertFalse(is_link_only("https://a.com https://b.com"))

    def test_non_http_text(self) -> None:
        self.assertFalse(is_link_only("just some text"))

    def test_empty_string(self) -> None:
        self.assertFalse(is_link_only(""))

    def test_whitespace_only(self) -> None:
        self.assertFalse(is_link_only("   \n  "))

    def test_ftp_scheme(self) -> None:
        self.assertFalse(is_link_only("ftp://files.example.com/data"))

    def test_no_netloc(self) -> None:
        self.assertFalse(is_link_only("https://"))

    def test_url_surrounded_by_angle_brackets(self) -> None:
        # <url> is not a bare URL
        self.assertFalse(is_link_only("<https://example.com>"))

    def test_url_with_newline_in_middle(self) -> None:
        self.assertFalse(is_link_only("https://example.com\nhttps://other.com"))


if __name__ == "__main__":
    unittest.main()
