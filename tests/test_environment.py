"""Test environment-file loading without accessing real credentials."""

import unittest
from unittest.mock import patch

from amc.youtube.api_client import CollectionError, YouTubeAPIClient


class EnvironmentTests(unittest.TestCase):
    @patch("amc.youtube.api_client.os.getenv", return_value="offline-placeholder")
    @patch("amc.youtube.api_client.load_dotenv")
    def test_root_env_is_loaded_without_overriding_environment(self, loader, getenv):
        client = YouTubeAPIClient()
        try:
            args, kwargs = loader.call_args
            self.assertEqual(args[0].name, ".env")
            self.assertEqual(kwargs, {"override": False})
        finally:
            client.close()

    @patch("amc.youtube.api_client.load_dotenv")
    def test_explicit_key_does_not_read_env_file(self, loader):
        client = YouTubeAPIClient(api_key="offline-placeholder")
        client.close()
        loader.assert_not_called()

    @patch("amc.youtube.api_client.os.getenv", return_value="")
    @patch("amc.youtube.api_client.load_dotenv")
    def test_missing_key_has_safe_setup_message(self, loader, getenv):
        with self.assertRaisesRegex(CollectionError, "Set YOUTUBE_API_KEY"):
            YouTubeAPIClient()
