"""Credentials from .env: WYKOP_KEY, WYKOP_SECRET and WYKOP_SALT; AMC_USER_AGENT optionally."""

import os
from pathlib import Path

from dotenv import load_dotenv

from amc.jobs.client import DEFAULT_USER_AGENT
from amc.wykop.client import WykopClient
from amc.wykop.records import RowBuilder
from amc.youtube.api_client import CollectionError


def connect(env_file: Path) -> tuple[WykopClient, RowBuilder]:
    load_dotenv(env_file, override=False)
    key, secret, salt = (
        os.getenv(name, "") for name in ("WYKOP_KEY", "WYKOP_SECRET", "WYKOP_SALT")
    )
    if not (key and secret and salt):
        raise CollectionError(
            "Set WYKOP_KEY, WYKOP_SECRET and WYKOP_SALT in .env before collecting."
        )
    user_agent = os.getenv("AMC_USER_AGENT", DEFAULT_USER_AGENT)
    return WykopClient(key, secret, user_agent=user_agent), RowBuilder(salt)
