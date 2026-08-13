from fastapi import APIRouter, HTTPException, Query
from app.database import get_db_connection
from urllib.parse import quote
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/drivers", tags=["Drivers"])

@router.get("/nearby-routes")
async def get_nearby_routes(
    supplier_id: str,
    radius_km: float = Query(5.0, ge=1.0, le=30.0, description="Search radius in kilometers")
):
    """
    Finds active supply listings for a supplier, queries pending requests within 
    the given radius using PostGIS ST_DWithin, and builds a Google Maps multi-stop URL.
    """
    conn = await get_db_connection()
    try:
        # 1. Fetch active supply listing for this supplier
        supply = await conn.fetchrow(
            """
            SELECT id, category, food_type, quantity, expires_at,
                   ST_Y(location::geometry) AS lat,
                   ST_X(location::geometry) AS lon
            FROM supplies
            WHERE supplier_id = $1::uuid AND status = 'AVAILABLE' AND expires_at > CURRENT_TIMESTAMP
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            supplier_id
        )

        if not supply:
            raise HTTPException(status_code=404, detail="No active, unexpired supplies found for this supplier.")

        supplier_lat = supply['lat']
        supplier_lon = supply['lon']
        category = supply['category']
        food_type = supply['food_type']

        # Enforce perishability rules on radius
        radius_meters = radius_km * 1000
        if food_type == 'COOKED' and radius_km > 5.0:
            # Hard-cap cooked food search to max 5km for food safety
            radius_meters = 5000.0

        # 2. Query pending requests within the radius using PostGIS spatial indexing
        requests = await conn.fetch(
            """
            SELECT 
                r.id AS request_id,
                r.quantity_requested,
                r.is_sos,
                r.otp_code,
                u.full_name AS requester_name,
                u.phone_number AS requester_phone,
                ST_Y(r.location::geometry) AS lat,
                ST_X(r.location::geometry) AS lon,
                ST_Distance(
                    r.location, 
                    ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography
                ) AS distance_meters
            FROM requests r
            JOIN users u ON r.requester_id = u.id
            WHERE r.status = 'PENDING'
              AND r.category = $3
              AND ST_DWithin(
                  r.location, 
                  ST_SetSRID(ST_MakePoint($1, $2), 4326)::geography, 
                  $4
              )
            ORDER BY r.is_sos DESC, distance_meters ASC
            LIMIT 9;
            """,
            supplier_lon, supplier_lat, category, radius_meters
        )

        if not requests:
            return {
                "status": "success",
                "message": "No matching pending requests found within range.",
                "supply_info": dict(supply),
                "matched_requests": []
            }

        # 3. Construct Google Maps Universal URL Deep Link
        # Format: https://www.google.com/maps/dir/?api=1&origin=LAT,LON&destination=LAT,LON&waypoints=LAT1,LON1|LAT2,LON2
        origin = f"{supplier_lat},{supplier_lon}"
        destination = f"{requests[-1]['lat']},{requests[-1]['lon']}"
        
        waypoints_str = ""
        if len(requests) > 1:
            # Intermediate stops before the final destination
            waypoint_coords = [f"{r['lat']},{r['lon']}" for r in requests[:-1]]
            waypoints_str = f"&waypoints={'|'.join(waypoint_coords)}"

        google_maps_url = (
            f"https://www.google.com/maps/dir/?api=1"
            f"&origin={quote(origin)}"
            f"&destination={quote(destination)}"
            f"{waypoints_str}"
            f"&travelmode=driving"
        )

        formatted_requests = []
        for r in requests:
            req_dict = dict(r)
            req_dict["distance_km"] = round(r["distance_meters"] / 1000, 2)
            # Add telephone link for pre-flight call verification
            req_dict["phone_call_link"] = f"tel:{r['requester_phone']}"
            formatted_requests.append(req_dict)

        return {
            "status": "success",
            "supply_id": str(supply["id"]),
            "matched_count": len(requests),
            "google_maps_navigation_url": google_maps_url,
            "requests": formatted_requests
        }

    finally:
        await conn.close()


@router.post("/verify-delivery")
async def verify_delivery(request_id: str, input_otp: str):
    """
    Validates the 4-digit OTP provided by the requester upon physical delivery.
    """
    conn = await get_db_connection()
    try:
        # Check matching request and OTP
        req = await conn.fetchrow(
            "SELECT otp_code, status FROM requests WHERE id = $1::uuid;",
            request_id
        )

        if not req:
            raise HTTPException(status_code=404, detail="Request ID not found.")

        if req["otp_code"] != input_otp:
            raise HTTPException(status_code=400, detail="Invalid OTP code. Delivery verification failed.")

        # Mark request as DELIVERED
        await conn.execute(
            "UPDATE requests SET status = 'DELIVERED', updated_at = CURRENT_TIMESTAMP WHERE id = $1::uuid;",
            request_id
        )

        return {"status": "success", "message": "Delivery verified successfully! Order marked as DELIVERED."}

    finally:
        await conn.close()

class AcceptRoutePayload(BaseModel):
    driver_id: str
    supply_id: str
    request_id: str

@router.post("/accept-route")
async def accept_route(payload: AcceptRoutePayload):
    """
    Locks a request by setting status='IN_TRANSIT' and deducts the requested 
    quantity from the supplier's active inventory in a safe database transaction.
    """
    conn = await get_db_connection()
    async with conn.transaction():  # Use DB transaction so both updates succeed or fail together
        # 1. Fetch current supply and request data with lock
        supply = await conn.fetchrow(
            "SELECT quantity, status FROM supplies WHERE id = $1::uuid FOR UPDATE;",
            payload.supply_id
        )
        request = await conn.fetchrow(
            "SELECT quantity_requested, status FROM requests WHERE id = $1::uuid FOR UPDATE;",
            payload.request_id
        )

        if not supply or supply["status"] != "AVAILABLE":
            raise HTTPException(status_code=400, detail="Supply is no longer available.")

        if not request or request["status"] != "PENDING":
            raise HTTPException(status_code=400, detail="Request has already been accepted by another driver or cancelled.")

        requested_qty = request["quantity_requested"]
        available_qty = supply["quantity"]

        if available_qty < requested_qty:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient inventory. Only {available_qty} items left, but request demands {requested_qty}."
            )

        # 2. Deduct inventory quantity
        new_qty = available_qty - requested_qty
        new_supply_status = "CLAIMED" if new_qty == 0 else "AVAILABLE"

        await conn.execute(
            """
            UPDATE supplies 
            SET quantity = $1, status = $2 
            WHERE id = $3::uuid;
            """,
            new_qty, new_supply_status, payload.supply_id
        )

        # 3. Transition request status to IN_TRANSIT
        await conn.execute(
            """
            UPDATE requests 
            SET status = 'IN_TRANSIT', updated_at = CURRENT_TIMESTAMP 
            WHERE id = $1::uuid;
            """,
            payload.request_id
        )

        return {
            "status": "success",
            "message": "Route accepted successfully! Request is now IN_TRANSIT.",
            "remaining_supply_quantity": new_qty,
            "request_status": "IN_TRANSIT"
        }