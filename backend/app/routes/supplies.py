from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from app.database import get_db_connection
from app.schemas import SupplyCreate, SupplyUpdate, FoodType

router = APIRouter(prefix="/api/v1/supplies", tags=["Supplies"])

@router.post("")
async def create_supply(supply: SupplyCreate):
    now = datetime.now(timezone.utc)
    
    if supply.food_type == FoodType.COOKED:
        expires_at = now + timedelta(hours=6)
    elif supply.food_type == FoodType.PACKAGED:
        expires_at = now + timedelta(days=30)
    else:
        expires_at = now + timedelta(days=90)
        
    conn = await get_db_connection()
    try:
        supply_id = await conn.fetchval(
            """
            INSERT INTO supplies (supplier_id, category, food_type, quantity, expires_at, location)
            VALUES ($1::uuid, $2, $3, $4, $5, ST_SetSRID(ST_MakePoint($6, $7), 4326)::geography)
            RETURNING id;
            """,
            supply.supplier_id, supply.category, supply.food_type.value, 
            supply.quantity, expires_at, supply.longitude, supply.latitude
        )
        return {"status": "success", "supply_id": str(supply_id), "expires_at": expires_at.isoformat()}
    finally:
        await conn.close()

@router.patch("/{supply_id}")
async def update_supply_inventory(supply_id: str, payload: SupplyUpdate):
    """Allows suppliers to edit remaining quantities or mark stock as expired/distributed."""
    conn = await get_db_connection()
    try:
        existing = await conn.fetchrow("SELECT id FROM supplies WHERE id = $1::uuid;", supply_id)
        if not existing:
            raise HTTPException(status_code=404, detail="Supply listing not found.")

        updates = []
        params = [supply_id]
        c = 2

        if payload.quantity is not None:
            updates.append(f"quantity = ${c}")
            params.append(payload.quantity)
            c += 1
            if payload.quantity == 0:
                updates.append("status = 'DISTRIBUTED_OFFLINE'")

        if payload.status is not None:
            updates.append(f"status = ${c}")
            params.append(payload.status)
            c += 1

        if not updates:
            raise HTTPException(status_code=400, detail="No fields provided for update.")

        updates.append("updated_at = CURRENT_TIMESTAMP")
        query = f"UPDATE supplies SET {', '.join(updates)} WHERE id = $1::uuid RETURNING id, quantity, status;"

        updated_row = await conn.fetchrow(query, *params)
        return {"status": "success", "data": dict(updated_row)}
    finally:
        await conn.close()