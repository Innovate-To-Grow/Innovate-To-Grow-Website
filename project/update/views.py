from datetime import date
from flask import Blueprint, render_template, url_for, request
from project import wks
from project.util.email import send_email
from project.util.token import confirm_token_no_expiry, generate_token
from project.update.forms import EmailForm, UpdateForm

update_blueprint = Blueprint("update", __name__, template_folder='templates', static_folder='static')

# check the database to see if the input email has a user with a registered prim. or secon. email
@update_blueprint.route('/update', methods=['GET', 'POST'])
def enter_email():
    form = EmailForm()

    if request.method == 'POST' and form.validate_on_submit():
        user = wks.find(request.form['email'], in_column=6)
        if user is not None:
            user = wks.row_values(user.row)
 
        if user == None:
            user = wks.find(request.form['email'], in_column=7)
            if user is not None:
                user = wks.row_values(user.row)

        # if the email entered is neither a primary nor secondary in the db, throw error message
        if user == None:
            return render_template("instructions_sent.html")

        # the verification status of the user's primary and secondary emails.
        verif1 = user[7]
        verif2 = user[8]

        if verif1 == 'FALSE' and verif2 == 'TRUE':
            # send an update link to the secondary and a verification link to primary
            p_token = generate_token(user[5])
            confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", confirm_url=confirm_url)
            p_subject = "i2G - Confirm Your Email Address"

            s_token = generate_token(user[6])
            update_url = url_for("update.update_info", token=s_token, _external=True)
            s_html = render_template("update_email.html", update_url=update_url)
            s_subject = "i2G - Link to Update Your Information"

            send_email(user[5], p_subject, p_html)
            send_email(user[6], s_subject, s_html)

            return render_template("instructions_sent.html")

        if verif1 == 'TRUE' and verif2 == 'FALSE':
            # send an update link to primary and verification to secondary
            p_token = generate_token(user[5])
            update_url = url_for("update.update_info", token=p_token, _external=True)
            p_html = render_template("update_email.html", update_url=update_url)
            p_subject = "i2G - Link to Update Your Information"

            token = generate_token(user[6])
            confirm_url = url_for("registration.confirm_secondary", token=token, _external=True)
            s_html = render_template("verify.html", confirm_url=confirm_url)
            s_subject = "i2G - Confirm Your Email Address"

            send_email(user[5], p_subject, p_html)
            send_email(user[6], s_subject, s_html)

            return render_template("instructions_sent.html")

        if verif1 == 'FALSE' and verif2 == 'FALSE':
            # user is in db, but not verified. send them links to verify both.
            p_token = generate_token(user[5])
            p_confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", confirm_url=p_confirm_url)

            s_token = generate_token(user[6])
            s_confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            s_html = render_template("verify.html", confirm_url=s_confirm_url)

            subject = "i2G - Confirm Your Email Address"
            send_email(user[5], subject, p_html)
            send_email(user[6], subject, s_html)

            return render_template("instructions_sent.html")

        if user[9] == "FALSE":
            token = generate_token(form.email.data)
            subject = "i2G - Complete Your Registration"
            info_url = url_for("registration.info", token=token, _external=True)
            html = render_template("need_info.html", info_url=info_url)

            send_email(form.email.data, subject, html)

            return render_template("instructions_sent.html")

        else:
            token = generate_token(form.email.data)
            subject = "i2G - Link to Update Your Information"
            update_url = url_for("update.update_info", token=token, _external=True)
            html = render_template("update_email.html", update_url=update_url)

            send_email(form.email.data, subject, html)

            return render_template("instructions_sent.html")

    else:
        return render_template("enter_email.html", form=form)
    

@update_blueprint.route('/enter_update/<token>', methods=['GET', 'POST'])
def update_info(token):
    email = confirm_token_no_expiry(token)
    user = wks.find(email, in_column=6)

    if user is not None:
        user = wks.row_values(user.row)
    if user == None:
        user = wks.find(email, in_column=7)
        if user is not None:
            user = wks.row_values(user.row)
    
    primary_temp = False
    if user[10] == "TRUE":
        primary_temp = True

    secondary_temp = False
    if user[11] == "TRUE":
        secondary_temp = True

    form = UpdateForm(first_name = user[1],
                      last_name = user[2],
                      primary_email = user[5],
                      secondary_email = user[6],
                      primary_subscribe = primary_temp,
                      secondary_subscribe = secondary_temp,
                      titlerole = user[12],
                      organization = user[13],
                      phonenumber = user[14])
   

    if request.method == 'POST' and form.validate_on_submit():
        cell_find = wks.find(email)
        cell_row_find = cell_find.row
        
        error = False
        swap = False
        need_verif = False
        sent_to_prim = False
        sent_to_sec = False
        
        subject = "i2G - Confirm Your Email Address"
        user_prim1 = wks.find(request.form['primary_email'], in_column=6)
        user_prim2 = wks.find(request.form['primary_email'], in_column=7)
        user_sec1 = wks.find(request.form['secondary_email'], in_column=6)
        user_sec2 = wks.find(request.form['secondary_email'], in_column=7)
    
        if (user_prim1 is not None or user_prim2 is not None or user_sec1 is not None or user_sec2 is not None):
            error = True

        if user[5] == request.form['primary_email'] or user[5] == request.form['secondary_email'] or user[6] == request.form['primary_email'] or user[6] == request.form['secondary_email']:
            error = False

        if error:
            return render_template("error.html")

        # primary AND secondary emails are swapped
        if user[5] == form.secondary_email.data and user[6] == form.primary_email.data:
            swap = True
            wks.update_cell(cell_row_find, 8, user[8])
            wks.update_cell(cell_row_find, 9, user[7])
            
        # primary OR secondary email are swapped
        elif user[5] == form.secondary_email.data:
            swap = True
            wks.update_cell(cell_row_find, 9, user[7])
            wks.update_cell(cell_row_find, 8, "FALSE")

            need_verif = True

            p_token = generate_token(form.primary_email.data)
            confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            html = render_template("verify.html", confirm_url=confirm_url)
            send_email(form.primary_email.data, subject, html)
            sent_to_prim = True
            
        elif user[6] == form.primary_email.data:
            swap = True
            wks.update_cell(cell_row_find, 8, user[8])
            wks.update_cell(cell_row_find, 9, "FALSE")

            need_verif = True

            s_token = generate_token(form.secondary_email.data)
            confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            html = render_template("verify.html", confirm_url=confirm_url)
            send_email(form.secondary_email.data, subject, html)
            sent_to_sec = True
            
        # changing primary to different email
        if user[5] != form.primary_email.data and not swap:
            need_verif = True

            if not sent_to_prim:
                p_token = generate_token(form.primary_email.data)
                confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
                html = render_template("verify.html", confirm_url=confirm_url)
                wks.update_cell(cell_row_find, 8, "FALSE")
                send_email(form.primary_email.data, subject, html)
                sent_to_prim = True

        # changing secondary to different email
        if user[6] != form.secondary_email.data and not swap:
            need_verif = True

            if not sent_to_sec:
                s_token = generate_token(form.secondary_email.data)
                confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
                html = render_template("verify.html", confirm_url=confirm_url)
                wks.update_cell(cell_row_find, 9, "FALSE")
                send_email(form.secondary_email.data, subject, html)
                sent_to_sec = True


        wks.update_cell(cell_row_find, 2, form.first_name.data)
        wks.update_cell(cell_row_find, 3, form.last_name.data)
        wks.update_cell(cell_row_find, 6, form.primary_email.data)
        wks.update_cell(cell_row_find, 7, form.secondary_email.data)
        wks.update_cell(cell_row_find, 13, form.titlerole.data)
        wks.update_cell(cell_row_find, 14, form.organization.data)
        wks.update_cell(cell_row_find, 15, form.phonenumber.data)
        
        
        user = wks.row_values(cell_row_find)
        
        if user[7] == "FALSE":
            wks.update_cell(cell_row_find, 11, "FALSE")
            if not sent_to_prim:
                need_verif = True
                p_token = generate_token(form.primary_email.data)
                confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
                html = render_template("verify.html", confirm_url=confirm_url)
                send_email(form.primary_email.data, subject, html)
             
        if user[8] == "FALSE":
            wks.update_cell(cell_row_find, 12, "FALSE")
            if not sent_to_sec:
                need_verif = True
                s_token = generate_token(form.secondary_email.data)
                confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
                html = render_template("verify.html", confirm_url=confirm_url)
                send_email(form.secondary_email.data, subject, html)
        
        if user[7] == "TRUE":
            wks.update_cell(cell_row_find, 11, form.primary_subscribe.data)

        if user[8] == "TRUE":
            wks.update_cell(cell_row_find, 12, form.secondary_subscribe.data)


        wks.update_cell(cell_row_find, 5, str(date.today()))


        if need_verif:
            return render_template("need_verif.html")
        else:
            return render_template("thanks_update.html")

    else:
        return render_template("update_page.html", form=form, token=token)
