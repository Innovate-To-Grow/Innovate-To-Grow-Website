from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, render_template, url_for, request
from project import wks
from project.models import edit_form
from project.util.email import send_email, delete_email
from project.util.field import get_field, checkbox_get_choices
from project.util.token import confirm_token_no_expiry, generate_token
from project.update.forms import EmailForm, UpdateForm

update_blueprint = Blueprint("update", __name__, template_folder="templates", static_folder="static")

# check the database to see if the input email has a user with a registered prim. or secon. email
@update_blueprint.route("/update", methods=["GET", "POST"])
def enter_email():
    form = EmailForm()

    if request.method == "POST" and form.validate():
        user = wks.find(request.form["email"], in_column=6)
        if user != None:
            user = wks.row_values(user.row)
        if user == None:
            user = wks.find(request.form["email"], in_column=7)
            if user != None:
                user = wks.row_values(user.row)
            else: 
                return render_template("error3.html")

        if user[7] == "FALSE" and user[8] == "TRUE":
            # send an update link to the secondary and a verification link to primary
            p_token = generate_token(user[5])
            confirm_url = url_for("registration.confirm", token=p_token, _external=True)
            p_html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=confirm_url)
            p_subject = "i2G - Confirm Your Email Address"

            s_token = generate_token(user[6])
            update_url = url_for("update.update_info", token=s_token, _external=True)
            s_html = render_template("update_email.html", first=user[1], last=user[2], update_url=update_url)
            s_subject = "i2G - Link to Update Your Information"

            if user[5] != "":
                send_email(user[5], p_subject, p_html)

            if user[6] != "":
                send_email(user[6], s_subject, s_html)

        elif user[7] == "TRUE" and user[8] == "FALSE":
            # send an update link to primary and verification to secondary
            p_token = generate_token(user[5])
            update_url = url_for("update.update_info", token=p_token, _external=True)
            p_html = render_template("update_email.html", first=user[1], last=user[2], update_url=update_url)
            p_subject = "i2G - Link to Update Your Information"

            s_token = generate_token(user[6])
            confirm_url = url_for("registration.confirm", token=s_token, _external=True)
            s_html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=confirm_url)
            s_subject = "i2G - Confirm Your Email Address"

            if user[5] != "":
                send_email(user[5], p_subject, p_html)
                
            if user[6] != "":
                send_email(user[6], s_subject, s_html)

        elif user[7] == "FALSE" and user[8] == "FALSE":
            # user is in db, but not verified. send them links to verify both.
            p_token = generate_token(user[5])
            p_confirm_url = url_for("registration.confirm", token=p_token, _external=True)
            p_html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=p_confirm_url)

            s_token = generate_token(user[6])
            s_confirm_url = url_for("registration.confirm", token=s_token, _external=True)
            s_html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=s_confirm_url)

            subject = "i2G - Confirm Your Email Address"
            
            if user[5] != "":
                send_email(user[5], subject, p_html)

            if user[6] != "":
                send_email(user[6], subject, s_html)

        else:
            token = generate_token(form.email.data)
            subject = "i2G - Link to Update Your Information"
            update_url = url_for("update.update_info", token=token, _external=True)
            html = render_template("update_email.html", first=user[1], last=user[2], update_url=update_url)

            send_email(form.email.data, subject, html)

        return render_template("instructions_sent.html")

    else:
        return render_template("enter_form.html", form=form)
    

@update_blueprint.route("/enter_update/<token>", methods=["GET", "POST"])
def update_info(token):
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
    
    for row in edit_form.query.all():
        setattr(UpdateForm, row.label, get_field(row))

    primary_temp = False
    if user[10] == "TRUE":
        primary_temp = True

    secondary_temp = False
    if user[11] == "TRUE":
        secondary_temp = True

    person = {"first_name" : user[1], "last_name" : user[2], "primary_email" : user[5], 
              "secondary_email" : user[6], "primary_subscribe" : primary_temp, 
              "secondary_subscribe" : secondary_temp}

    for row in edit_form.query.all():
        col_find = wks.find(row.label, in_row=1).col
        if col_find > len(user):
            person.update([(row.label, "")])
        else:
            if row.field_type == "checkbox":
                keys = []
                if user[col_find - 1] != "":
                    choices = checkbox_get_choices(row.options)
                    for val in user[col_find - 1].split(" ; "):
                        key = [key for key, v in choices if v == val][0]
                        keys.append(key)
                person.update([(row.label, keys)])
            else:
                person.update([(row.label, user[col_find - 1])])

    form = UpdateForm(data = person)

    
    if request.method == "POST" and form.validate_on_submit():
        cell_find = wks.find(email, in_column=6)
        if cell_find == None:
            cell_find = wks.find(email, in_column=7)
        
        row_find = cell_find.row

        cells = []
        
        error = False
        swap = False
        need_verif = False
        sent_to_prim = False
        sent_to_sec = False
        
        subject = "i2G - Confirm Your Email Address"

        user_prim1 = wks.find(request.form["primary_email"], in_column=6)
        if user_prim1 is not None:
            row_prim1 = user_prim1.row
            user_prim1 = wks.row_values(row_prim1)

        user_prim2 = wks.find(request.form["primary_email"], in_column=7)
        if user_prim2 is not None:
            row_prim2 = user_prim2.row
            user_prim2 = wks.row_values(row_prim2)

        user_sec1 = wks.find(request.form["secondary_email"], in_column=6)
        if user_sec1 is not None:
            row_sec1 = user_sec1.row
            user_sec1 = wks.row_values(row_sec1)

        user_sec2 = wks.find(request.form["secondary_email"], in_column=7)
        if user_sec2 is not None:
            row_sec2 = user_sec2.row
            user_sec2 = wks.row_values(row_sec2)
    
        if user_prim1 != None or user_prim2 != None or user_sec1 != None or user_sec2 != None:
            error = True

        if (user[5] == request.form["primary_email"] and user[6] == request.form["secondary_email"]) or (user[5] == request.form["secondary_email"] and user[6] == request.form["primary_email"]):
            error = False

        if error:
            if user_prim1 != None and user_prim1[7] == "FALSE":
                process = Thread(target=delete_email, args=(row_prim1, 6, user_prim1[5]))
                process.start()

            if user_prim2 != None and user_prim2.row[8] == "FALSE": 
                process = Thread(target=delete_email, args=(row_prim2, 7, user_prim2[6]))
                process.start()

            if user_sec1 != None and user_sec1[7] == "FALSE":
                process = Thread(target=delete_email, args=(row_sec1, 6, user_sec1[5]))
                process.start()

            if user_sec2 != None and user_sec2[8] == "FALSE":
                process = Thread(target=delete_email, args=(row_sec2, 7, user_sec2[6]))
                process.start()
            
            return render_template("error4.html")

        # primary AND secondary emails are swapped
        if user[5] == form.secondary_email.data and user[6] == form.primary_email.data:
            swap = True
            cells.append(Cell(row_find, 8, user[8]))
            cells.append(Cell(row_find, 9, user[7]))
            
        # primary OR secondary email are swapped
        elif user[5] == form.secondary_email.data:
            swap = True
            cells.append(Cell(row_find, 9, user[7]))
            cells.append(Cell(row_find, 8, "FALSE"))

            need_verif = True

            p_token = generate_token(form.primary_email.data)
            confirm_url = url_for("registration.confirm", token=p_token, _external=True)
            html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=confirm_url)
            send_email(form.primary_email.data, subject, html)
            sent_to_prim = True
            
        elif user[6] == form.primary_email.data:
            swap = True
            cells.append(Cell(row_find, 8, user[8]))
            cells.append(Cell(row_find, 9, "FALSE"))

            need_verif = True

            s_token = generate_token(form.secondary_email.data)
            confirm_url = url_for("registration.confirm", token=s_token, _external=True)
            html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=confirm_url)
            send_email(form.secondary_email.data, subject, html)
            sent_to_sec = True
            
        # changing primary to different email
        if user[5] != form.primary_email.data and not swap:
            need_verif = True

            if not sent_to_prim:
                p_token = generate_token(form.primary_email.data)
                confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=confirm_url)
                cells.append(Cell(row_find, 8, "FALSE"))
                send_email(form.primary_email.data, subject, html)
                sent_to_prim = True

        # changing secondary to different email
        if user[6] != form.secondary_email.data and not swap:
            need_verif = True

            if not sent_to_sec:
                s_token = generate_token(form.secondary_email.data)
                confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=confirm_url)
                cells.append(Cell(row_find, 9, "FALSE"))
                send_email(form.secondary_email.data, subject, html)
                sent_to_sec = True

        cells.append(Cell(row_find, 2, form.first_name.data))
        cells.append(Cell(row_find, 3, form.last_name.data))
        cells.append(Cell(row_find, 6, form.primary_email.data))
        cells.append(Cell(row_find, 7, form.secondary_email.data))

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
        
        wks.update_cells(cells)

        cells.clear()

        user = wks.row_values(row_find)
        
        if user[7] == "FALSE":
            cells.append(Cell(row_find, 11, "FALSE"))
            if not sent_to_prim:
                need_verif = True
                p_token = generate_token(form.primary_email.data)
                confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=confirm_url)
                send_email(form.primary_email.data, subject, html)
             
        if user[8] == "FALSE":
            cells.append(Cell(row_find, 12, "FALSE"))
            if not sent_to_sec:
                need_verif = True
                s_token = generate_token(form.secondary_email.data)
                confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                html = render_template("verify_email.html", first=user[1], last=user[2], confirm_url=confirm_url)
                send_email(form.secondary_email.data, subject, html)
        
        if user[7] == "TRUE":
            cells.append(Cell(row_find, 11, form.primary_subscribe.data))

        if user[8] == "TRUE":
            cells.append(Cell(row_find, 12, form.secondary_subscribe.data))

        cells.append(Cell(row_find, 5, str(datetime.now().replace(second=0, microsecond=0))))
        cells.append(Cell(row_find, 10, "TRUE"))

        wks.update_cells(cells)

        if need_verif:
            return render_template("need_verif.html")
        else:
            return render_template("thanks_update.html")

    else:
        return render_template("update_form.html", form=form, token=token)
