from flask import Flask, render_template, redirect, url_for, request
from project import app
from waitress import serve

app = Flask(__name__)

# Mock database to store collections (replace with actual database logic)
collections_db = []

@app.route('/create_collection', methods=['POST'])
def create_collection():
    # Simulate creating a new collection (replace with actual database logic)
    new_collection = {
        '_id': str(len(collections_db) + 1),  # Generate a new ID
        'title': request.form.get('title', 'New Collection')  # Get title from form data
    }
    # Save the collection to the mock database
    collections_db.append(new_collection)

    # Redirect to the account page with the new collection
    return redirect(url_for('account'))

# Mock function to simulate fetching a collection by ID
def get_collection_by_id(collection_id):
    # Replace this with your actual database query logic
    for collection in collections_db:
        if collection['_id'] == collection_id:
            return collection
    return None

@app.route('/account')
def account():
    # Fetch the latest collection (if any) from the mock database
    collection = collections_db[-1] if collections_db else None
    return render_template('account/account.html', email='user@example.com', collection=collection)

@app.route('/collection/<collection_id>')
def collection(collection_id):
    # Fetch the collection details using the collection_id
    collection = get_collection_by_id(collection_id)  # Replace with your database query
    if not collection:
        return "Collection not found", 404
    return render_template('home/collection.html', collection=collection)

if __name__ == "__main__":
    serve(app, host="0.0.0.0", port=5000, threads=8)