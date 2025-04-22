import asyncio, time
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, flash, render_template, url_for, request, redirect, copy_current_request_context, session, jsonify, Response
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField
from wtforms.validators import EqualTo, Email, InputRequired, Optional
from project import app, sh, wks, logs, tz, get_wks_records, get_wks_columns
from project.models import edit_form, event
from project.utils.email import send_email
from project.utils.dynamic_fields import get_field, checkbox_get_choices
from project.utils.token import generate_token, confirm_token
from project.forms.account_forms import LoginForm, SignupForm, ForgotPasswordForm, ResetPasswordForm, UpdatePasswordForm, UpdateEmailForm
import hashlib
from functools import wraps
from routes import add_user_direct
from routes import CONNECTION_STRING
from pymongo import MongoClient
import uuid

# Initialize MongoDB client and curated_lists collection
client = MongoClient(CONNECTION_STRING)
dbname = client['I2GUserDatabase']
curated_lists = dbname["curated_lists"]

account_blueprint = Blueprint("account",
                               __name__,
                               template_folder="../templates/account")

def update_user_token(email: str, token: str | None):
    #Update user's reset token in MongoDB
    collection = get_db_connection()
    result = collection.update_one(
        {"email": email},
        {"$set": {"token": token}}
    )
    return bool(result.modified_count)

def get_db_connection():
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    return dbname["users"]

def get_email(email):
    collection = get_db_connection()
    user = collection.find_one({"email": email})
    return user  # Returns None if not found

def get_access(user_id):
    collection = get_db_connection()
    user = collection.find_one({"_id": user_id})
    if not user:
        return None
    access = user.get("access", "")
    return access
    
#blocks logged in user from accessing certain resources by redirecting to profile page
def block_user(func):
    @wraps(func)  
    def wrapped_function(*args, **kwargs):
        if session.get("logged_in"):
            # If this is the login route with a POST request and a 'next' parameter
            # Allow the function to continue so proper redirection can happen
            if func.__name__ == 'login' and request.method == 'POST' and request.form.get('next'):
                # But return immediately after successful login
                result = func(*args, **kwargs)
                if isinstance(result, tuple) and len(result) > 1 and result[1] == 200:
                    # If the function succeeded without errors
                    return result
                
            # Otherwise show already logged in message
            flash("You are already logged in", "danger")
            return redirect(url_for("account.account"))
        
        return func(*args, **kwargs)
    return wrapped_function

#blocks guest from accessing certain resources by redirecting to login page
def block_guest(func):
    @wraps(func)
    def wrapped_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("You are not logged in", "danger")
            return redirect(url_for("account.login"))
        return func(*args, **kwargs)
    return wrapped_function

# Add a rate limiting helper function
def rate_limit(key, limit_seconds=10):
    """Check if operation is within rate limit window"""
    current_time = time.time()
    last_attempt = session.get(f"last_{key}_attempt", 0)
    
    if current_time - last_attempt < limit_seconds:
        # Too soon since last attempt
        return False
    
    # Update the timestamp of the last attempt
    session[f"last_{key}_attempt"] = current_time
    return True


@account_blueprint.route("/login", methods=["GET","POST"])
@block_user
def login():
    form = LoginForm()
    # Get collection parameter (not collection_id) from URL
    collection = request.args.get('collection')
    print(f"Debug - Login received collection: {collection}")
    
    if request.method == "GET":
        return render_template("login.html", form=form, collection=collection)

    if form.validate_on_submit():
        email = form.email.data.lower()
        user = get_email(email)

        if user:
            password = hashlib.sha256((email[::-1]+form.password.data).encode("utf-8")).hexdigest()
            if password == user["password"]:
                if user["verified"]:
                    # If there's collection data, update its ownership
                    collection = request.form.get('collection')
                    if collection:
                        try:
                            curated_lists.update_one(
                                {"_id": collection},
                                {"$set": {"userId": str(user["_id"])}}
                            )
                            print(f"Debug - Updated collection {collection} ownership to user {user['_id']}")
                            
                            # Set session and redirect back to the collection
                            session["logged_in"] = True
                            session["email"] = email
                            session.permanent = True
                            flash("Log in successful", "success")
                            # return redirect(url_for("home.past_projects", collection=collection))
                            return redirect(url_for("account.account"))
                        except Exception as e:
                            print(f"Debug - Error updating collection ownership: {str(e)}")
                    
                    session["logged_in"] = True
                    session["email"] = email
                    session.permanent = True
                    flash("Log in successful", "success")
                    return redirect(url_for("account.account"))

                # Check rate limiting (10 seconds between requests)
                if not rate_limit("verify_email", 10):
                    flash("Please wait a moment before requesting another verification email", "danger")
                    return render_template("login.html", form=form), 429

                token = generate_token(email)
                if update_user_token(email, token):
                    url = url_for("account.verify_email", token=token, _external=True)
                    email_template = render_template("account_verification_email.html", url=url)
                    send_email(email, "Verify Your Email", email_template)
                    flash("Unverified account. A new verification has been sent to "+email, "danger")
                    return render_template("login.html", form=form), 403
                else:
                    flash("Error processing request", "danger")
                    return render_template("login.html", form=form), 500

            flash("Incorrect password", "danger")
            return render_template("login.html", form=form), 401

        flash("Account with this email doesn't exist", "danger")
        return render_template("login.html", form=form), 404

    return render_template("login.html", form=form), 400
    

@account_blueprint.route("/signup", methods=["GET","POST"])
@block_user
def signup():
    form = SignupForm()
    # Get collection_id from URL query parameter
    collection = request.args.get('collection')
    print(f"Debug - Received collection_id: {collection}")

    if request.method == "GET":
        # Pass collection_id to the template
        return render_template("signup.html", form=form, collection=collection)

    #POST
    if form.validate_on_submit():
        email = form.email.data.lower()
        #verify email doesnt exist
        if get_email(email):
            flash("Account with this email already exists", "danger")
            return render_template("signup.html", form=form), 409

        #hash password and prepare user data
        password = hashlib.sha256((email[::-1]+form.password.data).encode("utf-8")).hexdigest()
        timestamp = str(time.time())
        user_id = str(uuid.uuid4())  # Generate user ID
        
        user_database = get_db_connection()
        try:
            # Insert the user
            user_data = {
                "_id": user_id,
                "email": email,
                "password": password,
                "timestamp": timestamp,
                "verified": False,
                "access": "user",
                "token": None
            }
            user_database.insert_one(user_data)
            
            # Get collection_id from form data
            collection = request.form.get('collection')
            
            # Update collection ownership if collection_id exists
            if collection:
                curated_lists.update_one(
                    {"_id": collection},
                    {"$set": {"userId": user_id}}
                )
            
            # Generate verification token and complete signup
            token = generate_token(email)
            if update_user_token(email, token):
                url = url_for("account.verify_email", token=token, _external=True)
                email_template = render_template("account_verification_email.html", url=url)
                send_email(email, "Verify Your Email", email_template)
                flash("Sign up successful. A verification email has been sent to "+email, "success")
                return redirect(url_for("account.login"))
            
        except Exception as e:
            print(f"Error in signup: {str(e)}")
            flash("Error creating account", "danger")
            return render_template("signup.html", form=form), 500

    return render_template("signup.html", form=form), 400


@account_blueprint.route("/forgot-password", methods=["GET","POST"])
@block_user
def forgot_password():
    form = ForgotPasswordForm()

    if request.method == "GET":
        return render_template("forgot_password.html", form=form)

    # POST
    if form.validate_on_submit():
        email = form.email.data.lower()
        
        # Check rate limiting
        if not rate_limit("password_reset", 10):
            flash("Please wait a moment before requesting another reset email", "danger")
            return render_template("forgot_password.html", form=form), 429
        
        # Verify email exists
        user = get_email(email)
        if user:
            # Generate and store token
            token = generate_token(email)
            if update_user_token(email, token):
                # Send password reset email
                url = url_for("account.reset_password", token=token, _external=True)
                email_template = render_template("password_reset_email.html", url=url)
                send_email(email, "Password Reset Requested", email_template)
                flash("Reset email has been sent to your address", "success")
                return redirect(url_for("account.login"))
            else:
                flash("Error processing request", "danger")
                return render_template("forgot_password.html", form=form), 500

        flash("No account found with this email address", "danger")
        return render_template("forgot_password.html", form=form), 404
        
    return render_template("forgot_password.html", form=form), 400


@account_blueprint.route("/reset-password/<token>", methods=["GET","POST"])
def reset_password(token):
    form = ResetPasswordForm()
    
    # Verify token
    email = confirm_token(token, 3600)
    if not email:
        return render_template("404.html"), 404

    # Verify token matches stored token
    user = get_email(email)
    if not user or user.get('token') != token:
        flash("Invalid or expired reset link", "danger")
        return render_template("404.html"), 404

    if request.method == "GET":
        return render_template("reset_password.html", form=form, token=token)
    
    # POST
    if form.validate_on_submit():
        # Hash new password
        password = hashlib.sha256((email[::-1]+form.password.data).encode("utf-8")).hexdigest()
        
        collection = get_db_connection()
        # Update password and clear token
        result = collection.update_one(
            {"email": email},
            {
                "$set": {"password": password},
                "$unset": {"token": ""}
            }
        )
        
        if result.modified_count:
            flash("Your password was reset", "success")
            return redirect(url_for("account.login"))
        else:
            flash("Error resetting password", "danger")
            return render_template("reset_password.html", form=form, token=token), 500

    return render_template("reset_password.html", form=form, token=token), 400


@account_blueprint.route("/verify-email/<token>")
@block_user
def verify_email(token):
    #verify valid and unexpired (1 hour) token
    email = confirm_token(token, 3600)
    if not email:
        return render_template("404.html"), 404

    user = get_email(email)
    if not user or user.get('token') != token:
        flash("Invalid or expired verification link", "danger")
        return render_template("404.html"), 404

    # Update verified status in MongoDB
    collection_name = get_db_connection()

    result = collection_name.update_one(
        {"email": email},
        {"$set": {"verified": True},
         "$unset": {"token": ""}
        }
    )
    
    if result.modified_count:
        flash("Your email has been verified", "success")
        return redirect(url_for("account.login"))
    else:
        flash("Error verifying email", "danger")
        return render_template("404.html"), 500


@account_blueprint.route("/account")
@block_guest
def account():
    # Get the current user's email from the session
    email = session.get("email")
    if not email:
        return redirect(url_for("account.login"))

    # Fetch the user document to get the user ID
    user = get_email(email)
    if not user:
        flash("User not found", "danger")
        return redirect(url_for("account.login"))

    user_id = str(user["_id"])

    # Get pagination and sorting parameters
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    sort_field = request.args.get('sort', 'createdAt')  # Default sort by creation date
    sort_order = request.args.get('order', 'desc')  # Default to newest first

    # Define the sort parameters for MongoDB
    sort_params = []
    if sort_field == 'title':
        sort_params.append(('title', 1 if sort_order == 'asc' else -1))
    elif sort_field == 'createdAt':
        sort_params.append(('createdAt', 1 if sort_order == 'asc' else -1))
    
    # If no sort specified, default to creation date descending
    if not sort_params:
        sort_params = [('createdAt', -1)]

    # Query the database with sorting
    total_collections = curated_lists.count_documents({"userId": user_id})
    collections = curated_lists.find({"userId": user_id}).sort(sort_params).skip((page - 1) * per_page).limit(per_page)

    # Convert ObjectId to string for rendering in the template
    collections = [
        {**collection, "_id": str(collection["_id"])} 
        for collection in collections
    ]

    return render_template(
        "account.html",
        email=email,
        collections=collections,
        page=page,
        per_page=per_page,
        total_collections=total_collections,
        sort_field=sort_field,
        sort_order=sort_order
    )


@account_blueprint.route("/collection/<collection_id>/delete", methods=["GET"])
@block_guest
def delete_collection(collection_id):
    """Delete a collection from user's profile"""
    try:
        # Get current user's email from session
        email = session.get("email")
        if not email:
            flash("Not authenticated", "danger")
            return redirect(url_for("account.login"))

        # Get user details
        user = get_email(email)
        if not user:
            flash("User not found", "danger")
            return redirect(url_for("account.login"))

        # Only allow admins or collection owner to delete the collection
        # Delete collection if user is admin
        if user.get("access") == "admin":
            result = curated_lists.delete_one({
                "_id": collection_id
            })
        # Delete collection is user is owner
        else:
            result = curated_lists.delete_one({
                "_id": collection_id,
                "userId": str(user["_id"])
            })
        
        if result.deleted_count:
            flash("Collection deleted successfully", "success")
        else:
            flash("Collection not found", "danger")

        return redirect(request.referrer or url_for("account.account"))

    except Exception as e:
        print(f"Error deleting collection: {str(e)}")
        return redirect(request.referrer or url_for("account.account"))
    
@account_blueprint.route("/database-admin")
@block_guest
def admin():
    try:
        email = session.get("email")
        if not email:
            return redirect(url_for("account.login"))

        user = get_email(email)
        if not user or user.get('access') != 'admin':
            flash("Unauthorized access", "danger")
            return redirect(url_for("account.account"))

        # Get pagination parameters
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        view = request.args.get('view', 'users')
        
        # Get sorting parameters
        sort_field = request.args.get('sort')
        sort_order = request.args.get('order', 'asc')
        
        if view == 'users':
            # Get users with pagination and sorting
            user_database = get_db_connection()
            total_items = user_database.count_documents({})
            
            # Define sort parameters
            sort_params = []
            if sort_field == 'email':
                sort_params.append(('email', 1 if sort_order == 'asc' else -1))
            elif sort_field == 'id':
                sort_params.append(('_id', 1 if sort_order == 'asc' else -1))
            
            # Apply sorting if specified, otherwise use default sort by email
            if not sort_params:
                sort_params = [('email', 1)]
                
            users_cursor = user_database.find().sort(sort_params).skip((page - 1) * per_page).limit(per_page)
            items_list = list(users_cursor)
            
        else:
            # Curated Lists view with sorting
            user_database = get_db_connection()
            total_items = curated_lists.count_documents({})
            
            # Define sort parameters for collections
            sort_params = []
            if sort_field == 'userEmail':
                # First get all collections and then sort by user email
                collections_cursor = curated_lists.find()
                items_list = []
                for collection in collections_cursor:
                    collection['_id'] = str(collection['_id'])
                    # Correctly display collection owner when they are: Guest/DeletedUser/NoEmailUser
                    try:
                        if collection['userId'] is None:
                            collection['userEmail'] = 'Guest'
                        else:
                            user_obj = user_database.find_one({'_id': collection['userId']})
                            if user_obj:
                                user_email = user_obj.get('email', 'No Email For Account')
                                collection['userEmail'] = user_email
                            else:
                                collection['userEmail'] = 'Deleted Account'
                        items_list.append(collection)
                    except Exception as e:
                        print(f"Debug - Error processing collection: {str(e)}")
                
                # Sort the list by userEmail
                items_list.sort(
                    key=lambda x: x.get('userEmail', ''),
                    reverse=(sort_order == 'desc')
                )
                # Apply pagination after sorting
                start_idx = (page - 1) * per_page
                items_list = items_list[start_idx:start_idx + per_page]
            # Update createdAt sorting logic to consider collection.history[0].createdAt
            elif sort_field == 'createdAt':
                sort_order_mongo = 1 if sort_order == 'asc' else -1
                pipeline = [
                    {
                        "$addFields": {
                            "effectiveCreatedAt": {
                                "$ifNull": [
                                    { "$arrayElemAt": [ "$history.createdAt", 0 ] },
                                    "$createdAt"
                                ]
                            }
                        }
                    },
                    { "$sort": { "effectiveCreatedAt": sort_order_mongo } },
                    { "$skip": (page - 1) * per_page },
                    { "$limit": per_page }
                ]
                items_list = list(curated_lists.aggregate(pipeline))
                for collection in items_list:
                    collection['_id'] = str(collection['_id'])
                    # Correctly display collection owner when they are: Guest/DeletedUser/NoEmailUser
                    try:
                        if collection['userId'] is None:
                            collection['userEmail'] = 'Guest'
                        else:
                            user_obj = user_database.find_one({'_id': collection['userId']})
                            if user_obj:
                                user_email = user_obj.get('email', 'No Email For Account')
                                collection['userEmail'] = user_email
                            else:
                                collection['userEmail'] = 'Deleted Account'
                    except Exception as e:
                        print(f"Debug - Error processing collection: {str(e)}")

            else:
                sort_params = []
                if sort_field == 'title':
                    sort_params.append(('title', 1 if sort_order == 'asc' else -1))

                if not sort_params:
                    # Update createdAt sorting logic to consider collection.history[0].createdAt
                    sort_order_mongo = 1 if sort_order == 'asc' else -1
                    pipeline = [
                        {
                            "$addFields": {
                                "effectiveCreatedAt": {
                                    "$ifNull": [
                                        { "$arrayElemAt": [ "$history.createdAt", 0 ] },
                                        "$createdAt"
                                    ]
                                }
                            }
                        },
                        { "$sort": { "effectiveCreatedAt": sort_order_mongo } },
                        { "$skip": (page - 1) * per_page },
                        { "$limit": per_page }
                    ]
                    items_list = list(curated_lists.aggregate(pipeline))
                    for collection in items_list:
                        collection['_id'] = str(collection['_id'])
                        # Correctly display collection owner when they are: Guest/DeletedUser/NoEmailUser
                        try:
                            if collection['userId'] is None:
                                collection['userEmail'] = 'Guest'
                            else:
                                user_obj = user_database.find_one({'_id': collection['userId']})
                                if user_obj:
                                    user_email = user_obj.get('email', 'No Email For Account')
                                    collection['userEmail'] = user_email
                                else:
                                    collection['userEmail'] = 'Deleted Account'
                        except Exception as e:
                            print(f"Debug - Error processing collection: {str(e)}")
                else:
                    collections_cursor = curated_lists.find().sort(sort_params).skip((page - 1) * per_page).limit(per_page)
                    items_list = []
                    for collection in collections_cursor:
                        collection['_id'] = str(collection['_id'])
                        # Correctly display collection owner when they are: Guest/DeletedUser/NoEmailUser
                        try:
                            if collection['userId'] is None:
                                collection['userEmail'] = 'Guest'
                            else:
                                user_obj = user_database.find_one({'_id': collection['userId']})
                                if user_obj:
                                    user_email = user_obj.get('email', 'No Email For Account')
                                    collection['userEmail'] = user_email
                                else:
                                    collection['userEmail'] = 'Deleted Account'
                            items_list.append(collection)
                        except Exception as e:
                            print(f"Debug - Error processing collection: {str(e)}")

        # Calculate pagination info
        total_pages = (total_items + per_page - 1) // per_page
        has_next = page < total_pages
        has_prev = page > 1

        return render_template(
            "admin.html",
            email=email,
            collections=items_list if view == 'lists' else None,
            users=items_list if view == 'users' else None,
            page=page,
            total_pages=total_pages,
            has_next=has_next,
            has_prev=has_prev,
            per_page=per_page,
            current_view=view
        )

    except Exception as e:
        print(f"Debug - Error in admin route: {str(e)}")
        flash("Error retrieving data", "danger")
        return redirect(url_for("account.account"))

@account_blueprint.route("/database-admin/purge", methods=["POST"])
@block_guest
def purge_collections():
    """Purge all collections from the database"""
    try:
        # Get current user's email from session
        email = session.get("email")
        if not email:
            flash("Not authenticated", "danger")
            return redirect(url_for("account.login"))

        # Delete all collections
        result = curated_lists.delete_many({})
        
        print(f"Debug - Purged {result.deleted_count} collections")
        flash(f"Successfully purged {result.deleted_count} collections", "success")
        
    except Exception as e:
        print(f"Debug - Error purging collections: {str(e)}")
        flash("Error purging collections", "danger")
    
    return redirect(url_for("account.admin"))


@account_blueprint.route("/database-admin/delete-user/<user_id>", methods=["GET"])
@block_guest
def delete_admin_user(user_id):
    try:
        # Verify admin access
        email = session.get("email")
        admin_user = get_email(email)
        if not admin_user or admin_user.get('access') != 'admin':
            flash("Unauthorized access", "danger")
            return redirect(url_for("account.account"))

        # Don't allow admin to delete themselves
        if user_id == str(admin_user['_id']):
            flash("Cannot delete your own admin account", "danger")
            return redirect(url_for("account.admin", view='users'))

        # Delete user's collections first
        # curated_lists.delete_many({"userId": user_id})

        user_database = get_db_connection()
        
        # Then delete the user
        result = user_database.delete_one({"_id": user_id})
        
        if result.deleted_count:
            flash("User and their collections deleted successfully", "success")
        else:
            flash("User not found", "danger")

    except Exception as e:
        print(f"Debug - Error deleting user: {str(e)}")
        flash("Error deleting user", "danger")
    
    return redirect(url_for("account.admin", view='users'))


@account_blueprint.route("/logout")
def logout():  # Remove @block_guest decorator to avoid circular dependency
    # Store the referrer before clearing the session
    next_page = request.referrer or url_for('home.mainpage')
    
    # Explicitly redirect to login if logging out from settings page
    if 'settings' in request.referrer:
        next_page = url_for('account.login')
    
    # Don't redirect to signup/account pages
    if next_page and ('signup' in next_page or 'account' in next_page):
        next_page = url_for('home.mainpage')
    
    # Clear the session
    session.clear()
    flash("You have been logged out", "success")
    return redirect(next_page)

@account_blueprint.route("/get_user_id", methods=["GET"])
@block_guest
def get_user_id():
    email = session.get("email")
    if email:
        user = get_email(email)
        if user:
            return {"id": str(user["_id"])}
    return {"error": "User not found"}, 404

@account_blueprint.route("/check_access", methods=["GET"])
def check_access():
    """Get current user's access level"""
    email = session.get("email")
    if email:
        user = get_email(email)
        if user and "access" in user:
            return {"access": user["access"]}
    return {"access": None}


@account_blueprint.route("/settings")
@block_guest
def settings():
    password_form = UpdatePasswordForm()
    email_form = UpdateEmailForm()

    email = session.get("email")
    if not email:
        flash("You must be logged in to access settings.", "danger")
        return redirect(url_for("account.login"))
    return render_template("settings.html", email=email, form=password_form, email_form=email_form)


@account_blueprint.route("/update-password", methods=["POST"])
def update_password():
    password_form = UpdatePasswordForm()
    email_form = UpdateEmailForm()

    email = session.get("email")
    if not email:
        flash("You must be logged in to update password.", "danger")
        return redirect(url_for("account.login"))

    user = get_email(email)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("account.login"))

    if password_form.validate_on_submit():
        #hash and save new password in database
        password = hashlib.sha256((email[::-1]+password_form.password.data).encode("utf-8")).hexdigest()
        user_database = get_db_connection()
        result = user_database.update_one(
            {"email": email},
            {
                "$set": {"password": password}
            }
        )

        if result.modified_count:
            flash("Your password was updated", "success")
            return redirect(url_for("account.settings"))
        else:
            flash("Error updating password", "danger")
            return redirect(url_for("account.settings"))
    
    return render_template("settings.html", email=email, form=password_form, email_form=email_form), 400


@account_blueprint.route("/update-email", methods=["POST"])
def update_email():
    password_form = UpdatePasswordForm()
    email_form = UpdateEmailForm()

    #current email of the user
    email = session.get("email")
    if not email:
        flash("You must be logged in to update email.", "danger")
        return redirect(url_for("account.login"))

    user = get_email(email)
    if not user:
        flash("User not found.", "danger")
        return redirect(url_for("account.login"))

    if email_form.validate_on_submit():
        #new email submitted in form
        new_email = email_form.email.data.lower()

        if new_email == email:
            flash("This email is already connected to your account", "danger")
            return redirect(url_for("account.settings"))

        if get_email(new_email):
            flash("This email is already connected to another account", "danger")
            return redirect(url_for("account.settings"))

        #hash plaintext password with old email to authenticate the email update attempt
        old_password = hashlib.sha256((email[::-1]+email_form.password.data).encode("utf-8")).hexdigest()
        if old_password != user["password"]:
            flash("Incorrect password.", "danger")
            return redirect(url_for("account.settings"))

        #use new email to hash the plaintext password from form
        password = hashlib.sha256((new_email[::-1]+email_form.password.data).encode("utf-8")).hexdigest()
        #update email in database
        #update password in database so login continues functioning since the hashing salt (email address) has changed
        #update verified status to false in database so blocks login until new email verified
        user_database = get_db_connection()
        result = user_database.update_one(
            {"email": email},
            {
                "$set": {"password": password, "email":new_email, "verified":False}
            }
        )

        if result.modified_count:
            token = generate_token(new_email)
            if update_user_token(new_email, token):
                #send verification email after update email
                url = url_for("account.verify_email", token=token, _external=True)
                email_template = render_template("account_verification_email.html", url=url)
                send_email(new_email, "Verify Your Email", email_template)
                flash("Email updated successfully. A verification email has been sent to "+new_email, "success")
                #force log out user
                return redirect(url_for("account.logout"))
            else:
                flash("Error processing request", "danger")
                return redirect(url_for("account.logout"))

        else:
            flash("Error updating email", "danger")
            return redirect(url_for("account.settings"))

    return render_template("settings.html", email=email, form=password_form, email_form=email_form), 400



@account_blueprint.route("/delete-account", methods=["POST"])
def delete_account():
    email = session.get("email")
    if not email:
        return jsonify({"error":"You must be logged in to delete account","redirect":url_for("account.login")}), 401

    user = get_email(email)
    if not user:
        return jsonify({"error":"User not found","redirect":url_for("account.login")}), 404

    data = request.get_json()
    if not data or "password" not in data:
        return jsonify({"error": "No password provided"}), 400

    password = hashlib.sha256((email[::-1]+data.get("password")).encode("utf-8")).hexdigest()
    if password != user["password"]:
        return jsonify({"error":"Incorrect password"}), 401

    user_database = get_db_connection()
    result = user_database.delete_one({"email": email})
    if result.deleted_count:
        return jsonify({"message":"Account deletion successful","redirect":url_for("account.logout")})
    else:
        return jsonify({"error":"Account deletion failed"}), 500

