#replace database.json dummy database with mongodb

import asyncio, time
from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, flash, render_template, url_for, request, redirect, copy_current_request_context, session
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
import json
from functools import wraps

account_blueprint = Blueprint("account",
                               __name__,
                               template_folder="../templates/account")


def get_email(email):
    with open("database.json") as f:
        table = json.load(f)
    #returns dictionary or None if email not found
    return next((row for row in table if row["email"] == email), None)

#blocks logged in user from accessing certain resources by redirecting to temporary account page
def block_user(func):
    @wraps(func)  
    def wrapped_function(*args, **kwargs):
        if session.get("logged_in"):
            flash("You are already logged in", "danger")
            #temporary landing page after signing in
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


@account_blueprint.route("/login", methods=["GET","POST"])
@block_user
def login():
    form = LoginForm()

    if request.method == "GET":
        return render_template("login.html", form=form)

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
                    flash("Log in successful", "success")
                    #temporary landing page after signing in
                    return redirect(url_for("account.account"))
                
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

        #hash password and record signup
        password = hashlib.sha256((email[::-1]+form.password.data).encode("utf-8")).hexdigest()
        timestamp = str(time.time())
        row = {"email":email,"password":password,"timestamp":timestamp,"verified":False}
        with open("database.json","r+") as f:
            table = json.load(f)
            table.append(row)
            f.seek(0)
            json.dump(table,f,indent=4)
            f.truncate()
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

    #POST
    if form.validate_on_submit():
        email = form.email.data.lower()
        #verify email exists
        if get_email(email):
            #send password reset email
            token = generate_token(email)
            url = url_for("account.reset_password", token=token, _external=True)
            email_template = render_template("password_reset_email.html", url=url)
            send_email(email, "Password Reset Requested", email_template)
            flash("Check your email for a password reset link", "success")
            return render_template("forgot_password.html", form=form)

        flash("Account with this email doesn't exist", "danger")
        return render_template("forgot_password.html", form=form), 404
        
    else:
        return render_template("forgot_password.html", form=form), 400


@account_blueprint.route("/reset-password/<token>", methods=["GET","POST"])
def reset_password(token):
    form = ResetPasswordForm()
    #verify valid and unexpired (1 hour) token
    email = confirm_token(token, 3600)
    if not email:
        return render_template("404.html"), 404

    if request.method == "GET":
        return render_template("reset_password.html", form=form, token=token)
    
    #POST
    if form.validate_on_submit():
        #hash new password and update database
        password = hashlib.sha256((email[::-1]+form.password.data).encode("utf-8")).hexdigest()
        with open("database.json", "r+") as f:
            table = json.load(f)
            for row in table:
                if row["email"] == email:
                    row["password"] = password
                    break
            f.seek(0)
            json.dump(table,f,indent=4)
            f.truncate()
        flash("Your password was reset", "success")
        #redirect to login page
        return redirect(url_for("account.login"))

    else:
        return render_template("reset_password.html", form=form, token=token), 400
    

@account_blueprint.route("/verify-email/<token>")
@block_user
def verify_email(token):
    #verify valid and unexpired (1 hour) token
    email = confirm_token(token, 3600)
    if not email:
        return render_template("404.html"), 404
    #update verified status in database
    with open("database.json", "r+") as f:
        table = json.load(f)
        for row in table:
            if row["email"] == email:
                row["verified"] = True
                break
        f.seek(0)
        json.dump(table,f,indent=4)
        f.truncate()
    flash("Your email has been verified", "success")
    return redirect(url_for("account.login"))


@account_blueprint.route("/account")
@block_guest
def account():
    #temporary landing page after signing in
    return render_template("account.html", email=session.get("email"))


@account_blueprint.route("/logout")
@block_guest
def logout():
    session.clear()
    flash("You have been logged out", "success")
    return redirect(url_for("account.login"))