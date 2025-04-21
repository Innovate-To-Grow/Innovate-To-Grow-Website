from pymongo import MongoClient

CONNECTION_STRING = "mongodb+srv://***REMOVED_URL_CREDS***@i2guserdatabase.nthty.mongodb.net/"
DEFAULT_ACCESS = "user"

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