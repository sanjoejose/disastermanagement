from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.database import get_db_connection

app = FastAPI(
    title="Hyper-Local Disaster Relief API",
    version="1.0.0",
    description="Spatial routing and emergency supply matching engine using PostGIS."
)

# Enable CORS so your local frontend (port 5173) can communicate with the backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Disaster Relief API is running 🚀"}

@app.get("/api/v1/health")
async def health_check():
    """
    Executes a test query to confirm the backend can reach the PostGIS extension on Supabase.
    """
    try:
        conn = await get_db_connection()
        # Fetch the installed PostGIS extension details to verify setup
        postgis_version = await conn.fetchval("SELECT PostGIS_Full_Version();")
        await conn.close()
        
        return {
            "status": "online",
            "database": "connected",
            "postgis_info": postgis_version
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Database connection handshake failed: {str(e)}"
        )