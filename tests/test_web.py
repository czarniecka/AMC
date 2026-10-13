"""Render the browser interface without making model requests."""

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class WebTests(unittest.TestCase):
    def test_app_renders_comment_form(self):
        app = AppTest.from_file(str(Path("amc/web/app.py").resolve())).run(timeout=30)
        self.assertEqual(len(app.exception), 0)
        self.assertEqual(app.text_area[0].label, "Polish or English comment")
        self.assertEqual(app.button[0].label, "Classify")
