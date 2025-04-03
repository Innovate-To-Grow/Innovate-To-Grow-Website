#replace database.json dummy database with mongodb

import asyncio, time
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, flash, render_template, url_for, request, redirect, copy_current_request_context, session, jsonify
from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, BooleanField, RadioField
from wtforms.validators import EqualTo, Email, InputRequired, Optional
from project import app, sh, wks, logs, tz, get_wks_records, get_wks_columns
from project.models import edit_form, event
from project.utils.email import send_email
from project.utils.dynamic_fields import get_field, checkbox_get_choices
from project.utils.token import generate_token, confirm_token
from project.forms.account_forms import LoginForm, SignupForm, ForgotPasswordForm, ResetPasswordForm
import hashlib
from functools import wraps
from routes import add_user_direct
from routes import CONNECTION_STRING
from pymongo import MongoClient

# Initialize MongoDB client and curated_lists collection
client = MongoClient(CONNECTION_STRING)
dbname = client['I2GUserDatabase']
curated_lists = dbname["curated_lists"]

account_blueprint = Blueprint("account",
                               __name__,
                               template_folder="../templates/account")

def update_user_token(email: str, token: str | None):
    """Update user's reset token in MongoDB"""
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

#blocks logged in user from accessing certain resources by redirecting to temporary account page
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
    # Get next parameter or use referrer as fallback
    next_page = request.args.get('next') or request.referrer or url_for('home.mainpage')
    
    # Don't redirect back to login/signup/account pages
    if next_page and ('login' in next_page or 'signup' in next_page or 'account' in next_page or 'logout' in next_page):
        next_page = url_for('home.mainpage')

    if request.method == "GET":
        return render_template("login.html", form=form, next=next_page)

    #POST
    if form.validate_on_submit():
        email = form.email.data.lower()
        #verify email exists
        selected_row = get_email(email)

        if selected_row:
            password = hashlib.sha256((email[::-1]+form.password.data).encode("utf-8")).hexdigest()
            if password == selected_row["password"]:
                if selected_row["verified"]:
                    #set cookie
                    session["logged_in"] = True
                    session["email"] = email
                    session.permanent = True  # Make session last longer
                    flash("Log in successful", "success")
                    
                    # Use the next parameter from the form and perform a direct redirect
                    redirect_url = request.form.get('next') or next_page
                    
                    # Use 302 status code for proper redirect without intermediate page
                    return redirect(redirect_url, code=302)
                
                token = generate_token(email)
                url = url_for("account.verify_email", token=token, _external=True)
                email_template = render_template("account_verification_email.html", url=url)
                send_email(email, "Verify Your Email", email_template)
                flash("Unverified account. A new verification has been sent to "+email, "danger")
                return render_template("login.html", form=form), 403

            flash("Incorrect password", "danger")
            return render_template("login.html", form=form), 401

        flash("Account with this email doesn't exist", "danger")
        return render_template("login.html", form=form), 404

    else:
        return render_template("login.html", form=form), 400
    

@account_blueprint.route("/signup", methods=["GET","POST"])
@block_user
def signup():
    form = SignupForm()

    if request.method == "GET":
        return render_template("signup.html", form=form)

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
        
        # Add user to MongoDB
        success = asyncio.run(add_user_direct(email, password, timestamp, False))
        
        if not success:
            flash("Error creating account", "danger")
            return render_template("signup.html", form=form), 500

        #send verification email after signup
        token = generate_token(email)
        url = url_for("account.verify_email", token=token, _external=True)
        email_template = render_template("account_verification_email.html", url=url)
        send_email(email, "Verify Your Email", email_template)
        flash("Sign up successful. A verification email has been sent to "+email, "success")

        return redirect(url_for("account.login"))

    else:
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

    # Update verified status in MongoDB
    client = MongoClient(CONNECTION_STRING)
    dbname = client['I2GUserDatabase']
    collection_name = dbname["users"]
    
    result = collection_name.update_one(
        {"email": email},
        {"$set": {"verified": True}}
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

    # Query the database for collections associated with this user ID
    collections = curated_lists.find({"userId": user_id})

    # Convert ObjectId to string for rendering in the template
    collections = [
        {**collection, "_id": str(collection["_id"])} for collection in collections
    ]

    return render_template("account.html", email=email, collections=collections)


@account_blueprint.route("/logout")
def logout():  # Remove @block_guest decorator to avoid circular dependency
    # Store the referrer before clearing the session
    next_page = request.referrer or url_for('home.mainpage')
    
    # Don't redirect to login/account pages
    if next_page and ('login' in next_page or 'signup' in next_page or 'account' in next_page):
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

        # Delete the collection
        result = curated_lists.delete_one({
            "_id": collection_id,
            "userId": str(user["_id"])
        })

        if result.deleted_count:
            flash("Collection deleted successfully", "success")
        else:
            flash("Collection not found", "danger")

        return redirect(url_for("account.account"))

    except Exception as e:
        flash(f"Error deleting collection: {str(e)}", "danger")
        return redirect(url_for("account.account"))