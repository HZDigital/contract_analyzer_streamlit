"""Keep tests isolated from a developer's local Blob configuration."""

import os


# Settings reads .env for local Uvicorn usage. Empty process values take
# precedence so TestClient never starts a dispatcher against real storage.
os.environ["AZURE_STORAGE_ACCOUNT_URL"] = ""
os.environ["AZURE_STORAGE_CONNECTION_STRING"] = ""
