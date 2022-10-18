from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, render_template, url_for, request, redirect
from project import wks
from project.models import edit_form
from project.util.email import send_email, delete_email
from project.util.field import get_field, checkbox_get_choices
from project.util.token import confirm_token_no_expiry, generate_token, confirm_token
from project.registration.forms import RegistrationForm, InformationForm

registration_blueprint = Blueprint("registration", __name__, template_folder="templates", static_folder="static")

@registration_blueprint.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm()

    if request.method == "POST" and form.validate():
        user_prim1 = wks.find(request.form["primary_email"], in_column=6)
        if user_prim1 != None:
            row_prim1 = user_prim1.row
            user_prim1 = wks.row_values(row_prim1)
            
        user_prim2 = wks.find(request.form["primary_email"], in_column=7)
        if user_prim2 != None:
            row_prim2 = user_prim2.row
            user_prim2 = wks.row_values(row_prim2)
            
        user_sec1 = wks.find(request.form["secondary_email"], in_column=6)
        if user_sec1 != None:
            row_sec1 = user_sec1.row
            user_sec1 = wks.row_values(row_sec1)
            
        user_sec2 = wks.find(request.form["secondary_email"], in_column=7)
        if user_sec2 != None:
            row_sec2 = user_sec2.row
            user_sec2 = wks.row_values(row_sec2)
        
        if user_prim1 != None or user_prim2 != None or user_sec1 != None or user_sec2 != None:
            update_subject = "i2G - Link to Update Your Information"
            
            if user_prim1 != None and user_prim1[7] == "FALSE":
                process = Thread(target=delete_email, args=(row_prim1, 6, user_prim1[5]))
                process.start()  
    
            elif user_prim1 != None and user_prim1[7] == "TRUE":
                token = generate_token(user_prim1[5])
                update_url = url_for("update.update_info", token=token, _external=True)
                update_html = render_template("update_email.html", first=user_prim1[1], last=user_prim1[2], update_url=update_url)
                send_email(user_prim1[5], update_subject, update_html)

                
            if user_prim2 != None and user_prim2[8] == "FALSE":
                process = Thread(target=delete_email, args=(row_prim2, 7, user_prim2[6]))
                process.start()
       
            elif user_prim2 != None and user_prim2[8] == "TRUE":
                token = generate_token(user_prim2[6])
                update_url = url_for("update.update_info", token=token, _external=True)
                update_html = render_template("update_email.html", first=user_prim2[1], last=user_prim2[2], update_url=update_url)
                send_email(user_prim2[6], update_subject, update_html)


            if user_sec1 != None and user_sec1[7] == "FALSE":
                process = Thread(target=delete_email, args=(row_sec1, 6, user_sec1[5]))
                process.start()
                    
            elif user_sec1 != None and user_sec1[7] == "TRUE":
                token = generate_token(user_sec1[5])
                update_url = url_for("update.update_info", token=token, _external=True)
                update_html = render_template("update_email.html", first=user_sec1[1], last=user_sec1[2], update_url=update_url)
                send_email(user_sec1[5], update_subject, update_html)
                    
    
            if user_sec2 != None and user_sec2[8] == "FALSE":
                process = Thread(target=delete_email, args=(row_sec2, 7, user_sec2[6]))
                process.start()

            elif user_sec2 != None and user_sec2[8] == "TRUE":
                token = generate_token(user_sec2[6])
                update_url = url_for("update.update_info", token=token, _external=True)
                update_html = render_template("update_email.html", first=user_sec2[1], last=user_sec2[2], update_url=update_url)
                send_email(user_sec2[6], update_subject, update_html)
            

            return render_template("error1.html")


        else:
            user = [
                len(wks.col_values(1)), # Order
                form.first_name.data, # First Name
                form.last_name.data, # Last Name
                str(datetime.now().replace(second=0, microsecond=0)), # When Started
                str(datetime.now().replace(second=0, microsecond=0)), # Last Updated
                form.primary_email.data, # Primary Email
                form.secondary_email.data, # Secondary Email
                "FALSE", # Primary Status
                "FALSE", # Secondary Status
                "FALSE", # Info Completed
                "FALSE", # Primary Subscribed
                "FALSE"  # Secondary Subscribed
            ]

            wks.append_row(user)

            p_token = generate_token(user[5])
            p_confirm_url = url_for("registration.confirm", token=p_token, _external=True)
            p_html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=p_confirm_url)

            s_token = generate_token(user[6])
            s_confirm_url = url_for("registration.confirm", token=s_token, _external=True)
            s_html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=s_confirm_url)

            verif_subject = "i2G - Confirm Your Email Address"
            
            send_email(user[5], verif_subject, p_html)
            send_email(user[6], verif_subject, s_html)

            return render_template("instructions_sent.html")

    else:
        return render_template("register_form.html", form=form)


@registration_blueprint.route("/con<token>")
def confirm(token):
    user = None
    email = confirm_token(token)
    
    if email:
        user = wks.find(email, in_column=6)
        if user is not None:
            user_col = user.col
            user = wks.row_values(user.row)
        if user is None:
            user = wks.find(email, in_column=7)
            if user is not None:
                user_col = user.col
                user = wks.row_values(user.row)
            else: 
                return render_template("error2.html")

    if user == None:
        return render_template("resend.html", token=token, _external=True)

    elif user[user_col + 1] == "TRUE" and user[9] == "TRUE":
        return render_template("already_confirmed.html")

    else:
        cell_find = wks.find(email, in_column=6)
        if cell_find == None:
            cell_find = wks.find(email, in_column=7)

        row_find = cell_find.row
        col_find = cell_find.col

        cells = []
        cells.append(Cell(row_find, col_find + 2, "TRUE"))
        cells.append(Cell(row_find, col_find + 5, "TRUE"))

        wks.update_cells(cells)

        if user[9] == "FALSE":
            return redirect(url_for("registration.info", token=token, _external=True))
        else:
            return render_template("thanks_confirming.html")
        

@registration_blueprint.route("/res<token>")
def resend(token):
    email = confirm_token_no_expiry(token)

    if email:
        user = wks.find(email, in_column=6)
        if user != None:
            user = wks.row_values(user.row)
        if user == None:
            user = wks.find(email, in_column=7)
            if user != None:
                user = wks.row_values(user.row)
            else: 
                return render_template("error2.html")
    else:
        return render_template("error2.html")

    new_token = generate_token(email)
    url = url_for("registration.confirm", token=new_token, _external=True)
    html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=url)
    subject = "i2G - Confirm Your Email Address"
    send_email(email, subject, html)

    return render_template("resend.html", token=token, _external=True)


@registration_blueprint.route("/info/<token>", methods=["GET", "POST"])
def info(token):
    for row in edit_form.query.all():
        setattr(InformationForm, row.label, get_field(row))

    form = InformationForm()

    email = confirm_token_no_expiry(token)
    
    if email:
        user = wks.find(email, in_column=6)
        if user != None:
            user = wks.row_values(user.row)
        if user == None:
            user = wks.find(email, in_column=7)
            if user != None:
                user = wks.row_values(user.row)
            else: 
                return render_template("error2.html")
    else:
        return render_template("error2.html")


    if request.method == "POST" and form.validate_on_submit():
        if user[9] == "TRUE":
            return render_template("homepage.html")

        cell_find = wks.find(email, in_column=6)
        if cell_find == None:
            cell_find = wks.find(email, in_column=7)

        row_find = cell_find.row

        cells = []

        for row in edit_form.query.all():
            col_find = wks.find(row.label, in_row=1).col
            if row.field_type == "checkbox":
                vals = []
                choices = checkbox_get_choices(row.options)
                for key in request.form.getlist(row.label):
                    vals.append(choices[int(key)][1])
                cells.append(Cell(row_find, col_find, " ; ".join(vals)))
            else:
                cells.append(Cell(row_find, col_find, request.form[row.label]))

        cells.append(Cell(row_find, 10, "TRUE"))

        wks.update_cells(cells)
    
        return render_template("thanks_registering.html")

    else:
        return render_template("info_form.html", form=form, token=token)