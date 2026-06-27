import os
import tempfile

# Isolate the SQLite app store to a temp file and force local env BEFORE settings load.
os.environ["WB_SQLITE_PATH"] = os.path.join(tempfile.mkdtemp(prefix="wb-test-"), "test.db")
os.environ["WB_ENV"] = "local"
os.environ.setdefault("WB_JWT_SECRET", "test-secret-key-please")

from wanderbot.config import get_settings  # noqa: E402

get_settings.cache_clear()
