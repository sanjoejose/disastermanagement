from pydantic import BaseModel, Field, validator
from typing import Optional
from enum import Enum

# --- ENUMS ---
class UserRole(str, Enum):
    REQUESTER = "requester"
    SUPPLIER = "supplier"
    DRIVER = "driver"
    ADMIN = "admin"

class FoodType(str, Enum):
    COOKED = "COOKED"
    PACKAGED = "PACKAGED"
    NON_FOOD = "NON_FOOD"

# --- USER SCHEMAS ---
class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, example="Anjali Nair")
    phone_number: str = Field(..., min_length=10, max_length=15, example="+919876543210")
    role: UserRole

# --- SUPPLY SCHEMAS ---
class SupplyCreate(BaseModel):
    supplier_id: str
    category: str = Field(..., example="Prepared Meals")  # e.g., 'Prepared Meals', 'Drinking Water'
    food_type: FoodType = FoodType.NON_FOOD
    quantity: int = Field(..., gt=0, example=20)
    latitude: float = Field(..., ge=-90.0, le=90.0, example=9.9312)
    longitude: float = Field(..., ge=-180.0, le=180.0, example=76.2673)

# --- REQUEST SCHEMAS ---
class RequestCreate(BaseModel):
    requester_id: str
    headcount_adults: int = Field(1, ge=0)
    headcount_children: int = Field(0, ge=0)
    headcount_infants: int = Field(0, ge=0)
    category: str = Field(..., example="Drinking Water")
    quantity_requested: int = Field(..., gt=0)
    is_sos: bool = False
    latitude: float = Field(..., ge=-90.0, le=90.0, example=9.9350)
    longitude: float = Field(..., ge=-180.0, le=180.0, example=76.2600)