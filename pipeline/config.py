import os
from dotenv import load_dotenv

load_dotenv()

# These are required at runtime but not at import time.
# Missing values raise at the point of first use so dry-runs work without a .env.
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

SBIR_API_BASE = "https://api.sbir.gov/public/api"
SBIR_PAGE_SIZE = 250
SBIR_REQUEST_DELAY = 0.4  # seconds between paginated requests

EMBED_MODEL = "voyage-3"
EMBED_DIMENSIONS = 1024       # voyage-3 output dimension
EMBED_BATCH_SIZE = 128        # Voyage AI max per request

SBIR_AGENCIES = [a.strip() for a in os.getenv("SBIR_AGENCIES", "").split(",") if a.strip()]
SBIR_START_YEAR = int(os.getenv("SBIR_START_YEAR", "0")) or None
