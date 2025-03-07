from fastapi import APIRouter, Body, Request, Response, HTTPException, status
from fastapi.encoders import jsonable_encoder
from typing import List

from models import User

router = APIRouter()

@router.get("/add-user/", response_description="Add a user to database")
def create_user():
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

@router.get("/print-message/", response_description="Print a message")
def print_message():
    print('I was clicked from FastAPI!')
    return {"message": "Message printed to console from FastAPI."}

# @router.post("/signUp", response_description="Create a new user", status_code=status.HTTP_201_CREATED, response_model=User)
# def create_user(request: Request, user: User = Body(...)):
#     user = jsonable_encoder(user)
#     new_user = request.app.database["users"].insert_one(user)
#     created_user = request.app.database["users"].find_one(
#         {"_id": new_user.inserted_id}
#     )
#     return created_user

# @router.post("/", response_description="Create a new book", status_code=status.HTTP_201_CREATED, response_model=Book)
# def create_book(request: Request, book: Book = Body(...)):
#     book = jsonable_encoder(book)
#     new_book = request.app.database["books"].insert_one(book)
#     created_book = request.app.database["books"].find_one(
#         {"_id": new_book.inserted_id}
#     )

#     return created_book

# @router.get("/", response_description="List all books", response_model=List[Book])
# def list_books(request: Request):
#     books = list(request.app.database["books"].find(limit=100))
#     return books

# @router.get("/{id}", response_description="Get a single book by id", response_model=Book)
# def find_book(id: str, request: Request):
#     if (book := request.app.database["books"].find_one({"_id": id})) is not None:
#         return book
#     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Book with ID {id} not found")

# @router.put("/{id}", response_description="Update a book", response_model=Book)
# def update_book(id: str, request: Request, book: BookUpdate = Body(...)):
#     book = {k: v for k, v in book.dict().items() if v is not None}
#     if len(book) >= 1:
#         update_result = request.app.database["books"].update_one(
#             {"_id": id}, {"$set": book}
#         )

#         if update_result.modified_count == 0:
#             raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Book with ID {id} not found")

#     if (
#         existing_book := request.app.database["books"].find_one({"_id": id})
#     ) is not None:
#         return existing_book

#     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Book with ID {id} not found")

# @router.delete("/{id}", response_description="Delete a book")
# def delete_book(id: str, request: Request, response: Response):
#     delete_result = request.app.database["books"].delete_one({"_id": id})

#     if delete_result.deleted_count == 1:
#         response.status_code = status.HTTP_204_NO_CONTENT
#         return response

#     raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Book with ID {id} not found")