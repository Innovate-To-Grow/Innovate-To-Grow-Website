import threading
import uvicorn
from fastapi import FastAPI
from dotenv import dotenv_values
from pymongo import MongoClient
from routes import router as user_router

from contextlib import asynccontextmanager

from project import app

config = dotenv_values(".env")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    mongodb_client = MongoClient(config["ATLAS_URI"])
    app.database = mongodb_client[config["DB_NAME"]]
    yield
    # Shutdown
    mongodb_client.close()

# FastAPI setup
app_api = FastAPI(lifespan=lifespan)

# @app_api.get("/print-message-flask/")
# def print_message_fastapi():
#     print('I was clicked from FastAPI!')
#     return {"message": "Message printed to console from FastAPI."}

app_api.include_router(user_router, tags=["users"], prefix="/user")

@app.route('/add-user/')
def add_user_flask():
    CONNECTION_STRING = "mongodb+srv://***REMOVED_URL_CREDS***@i2guserdatabase.nthty.mongodb.net/"
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["users"]
    user_details = {
        "_id": "066de609-b04a-4b30-b46c-32537c7f1f6e",
        "name": "Doro",
        "role": "user"
    }
    collection_name.insert_one(user_details)
    return {"message": "User added to database."}

# @app.route('/print-message/')
# def print_message_flask():
#     print('I was clicked from Flask!')
#     return 'Message printed to console from Flask.'

def run_fastapi():
    uvicorn.run(app_api, host="0.0.0.0", port=8000, reload=True)

def run_flask():
    app.run(port=5000)

if __name__ == "__main__":
    threading.Thread(target=run_fastapi).start()
    threading.Thread(target=run_flask).start()