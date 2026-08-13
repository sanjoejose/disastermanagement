import os
import asyncpg
from dotenv import load_dotenv

# Load variables from the .env file
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

async def get_db_connection():
    """
    Establishes and returns an asynchronous connection to the Supabase PostGIS instance.
    """
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL is missing from environment variables.")
    
    # Establish connection via asyncpg
    conn = await asyncpg.connect(DATABASE_URL)
    return conn