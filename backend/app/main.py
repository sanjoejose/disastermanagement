from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from app.database import get_db_connection

# Import router modules
from app.routes.users import router as users_router
from app.routes.supplies import router as supplies_router
from app.routes.requests import router as requests_router
from app.routes.drivers import router as drivers_router  # <--- NEW

app = FastAPI(
    title="Hyper-Local Disaster Relief API",
    version="1.0.0",
    description="Spatial routing and emergency supply matching engine using PostGIS."
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
app.include_router(drivers_router)  # <--- NEW

@app.get("/")
async def root():
    return {"message": "Disaster Relief API is running 🚀"}

@app.get("/api/v1/health")
async def health_check():
    try:
        conn = await get_db_connection()
        version = await conn.fetchval("SELECT PostGIS_Full_Version();")
        await conn.close()
        return {"status": "online", "database": "connected", "postgis_info": version}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))