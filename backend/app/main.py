from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.database import get_db_connection

from app.routes.users import router as users_router
from app.routes.supplies import router as supplies_router
from app.routes.requests import router as requests_router
from app.routes.drivers import router as drivers_router
from app.routes.camps import router as camps_router

app = FastAPI(
    title="Hyper-Local Disaster Relief API",
    version="2.0.0",
    description="Spatial routing, evacuation matching, and relief camp navigation engine using PostGIS."
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Attach Routers
app.include_router(users_router)
app.include_router(supplies_router)
app.include_router(requests_router)
app.include_router(drivers_router)
app.include_router(camps_router)

@app.get("/")
async def root():
    return {"message": "Disaster Relief API v2.0 is running 🚀"}

@app.get("/api/v1/health")
async def health_check():
    try:
        conn = await get_db_connection()
        version = await conn.fetchval("SELECT PostGIS_Full_Version();")
        await conn.close()
        return {"status": "online", "database": "connected", "postgis_info": version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))