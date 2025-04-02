from fastapi import APIRouter, Query, HTTPException
from pymongo import MongoClient
import uuid

router = APIRouter()

CONNECTION_STRING = "mongodb+srv://***REMOVED_URL_CREDS***@i2guserdatabase.nthty.mongodb.net/"

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
        "verified": verified
    }
    
    try:
        collection_name.insert_one(user_details)
        return True
    except Exception as e:
        print(f"Error adding user: {e}")
        return False

@router.post("/save-curation/")
async def save_curation(curation: dict):
    """
    Save or update a curation in the MongoDB `curated_lists` collection.
    """
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["curated_lists"]

    # Check if the curation already exists (based on `_id`)
    if "_id" in curation:
        from bson import ObjectId
        # Convert `_id` to ObjectId if it's a valid ObjectId
        if ObjectId.is_valid(curation["_id"]):
            curation["_id"] = ObjectId(curation["_id"])
        else:
            # Keep `_id` as a string if it's not a valid ObjectId
            pass

        # Update the existing curation
        result = collection_name.update_one(
            {"_id": curation["_id"]},
            {"$set": curation},
            upsert=True
        )
        if result.upserted_id or result.modified_count:
            return {"message": "Curation saved successfully.", "id": str(curation["_id"])}
        else:
            raise HTTPException(status_code=500, detail="Failed to save curation.")
    else:
        # Insert a new curation
        curation["_id"] = str(uuid.uuid4())  # Generate a new UUID for the curation
        result = collection_name.insert_one(curation)
        return {"message": "Curation saved successfully.", "id": str(result.inserted_id)}