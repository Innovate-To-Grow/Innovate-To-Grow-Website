from fastapi import APIRouter, Query, HTTPException
from pymongo import MongoClient
import uuid

router = APIRouter()

CONNECTION_STRING = "mongodb+srv://***REMOVED_URL_CREDS***@i2guserdatabase.nthty.mongodb.net/"
DEFAULT_ACCESS = "user"

@router.get("/add-user/")
async def add_user(name: str = Query(...)):
    if not name:
        raise HTTPException(status_code=400, detail="No username provided")

    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["users"]

    user_details = {
        "_id": str(uuid.uuid4()),
        "name": name,
        "role": "user"
    }
    
    try:
        collection_name.insert_one(user_details)
        print(f"Added user: {name}")
        return {"message": f"User {name} added to database."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/read-user/")
async def read_user(name: str = Query(...)):
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["users"]

    user = collection_name.find_one({"name": name})
    if user:
        return {"id": str(user["_id"])}
    raise HTTPException(status_code=404, detail="User not found")

@router.get("/update-user/")
async def update_user(name: str = Query(...)):
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["users"]

    result = collection_name.update_one(
        {"name": name}, 
        {"$set": {"role": "admin"}}
    )
    if result.modified_count:
        return {"message": f"User {name} updated to admin."}
    raise HTTPException(status_code=404, detail="User not found")

@router.get("/delete-user/")
async def delete_user(name: str = Query(...)):
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["users"]
    
    result = collection_name.delete_one({"name": name})
    if result.deleted_count:
        return {"message": f"User {name} deleted from database."}
    raise HTTPException(status_code=404, detail="User not found")

# Function for direct usage
async def add_user_direct(email: str, password: str, timestamp: str, verified: bool = False):
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["users"]

    user_details = {
        "_id": str(uuid.uuid4()),
        "email": email,
        "password": password,
        "timestamp": timestamp,
        "verified": verified,
        "access": DEFAULT_ACCESS,
        "token": None
    }
    
    try:
        collection_name.insert_one(user_details)
        return True
    except Exception as e:
        print(f"Error adding user: {e}")
        return False
    
async def get_user_id(email: str):
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["users"]

    user = collection_name.find_one({"email": email})
    if user:
        return str(user["_id"])