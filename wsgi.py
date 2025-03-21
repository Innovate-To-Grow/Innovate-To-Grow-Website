import multiprocessing
import uvicorn
from fastapi import FastAPI
from pymongo import MongoClient
from routes import router as user_router
from contextlib import asynccontextmanager
from project import app

@asynccontextmanager
async def lifespan(app_api: FastAPI):
    mongodb_client = MongoClient("mongodb+srv://***REMOVED_URL_CREDS***@i2guserdatabase.nthty.mongodb.net/")
    app_api.database = mongodb_client['I2GUserDatabase']
    yield
    mongodb_client.close()

app_api = FastAPI(lifespan=lifespan)
app_api.include_router(user_router, prefix="/user", tags=["users"])

def run_fastapi():
    uvicorn.run(app_api, host="0.0.0.0", port=8000, reload=False)

def run_flask():
    app.run(port=5000, debug=True)

if __name__ == "__main__":
    # Create processes instead of threads
    fastapi_process = multiprocessing.Process(target=run_fastapi)
    flask_process = multiprocessing.Process(target=run_flask)
    
    # Start both processes
    fastapi_process.start()
    flask_process.start()
    
    # Wait for both processes to complete
    fastapi_process.join()
    flask_process.join()
    # app.run()
