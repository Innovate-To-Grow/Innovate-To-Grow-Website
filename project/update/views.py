from datetime import timedelta
from werkzeug.datastructures import MultiDict

from project.update.forms import EmailForm, UpdateForm
from flask import Blueprint, render_template, url_for, request
from flask_login import login_required, login_user, current_user
from project.models import member_roster
from project import db
from project.util.email import send_email
from project.util.token import confirm_token, generate_token
import gspread
sa = gspread.service_account()
sh = sa.open("I2G-Master-People")
wks = sh.worksheet("double-email-test")

update_blueprint = Blueprint("update", __name__, template_folder='templates',static_folder='static')

# check the database to see if the input email has a user with a registered prim. or secon. email
@update_blueprint.route('/update', methods=['GET', 'POST'])
def enter_email():
    form = EmailForm(request.form)

    if request.method == 'POST' and form.validate():
        user = wks.find(request.form['email'], in_column=4)
        if user is not None:
            user = wks.row_values(user.row)
        # user = member_roster.query.filter_by(primary_email=request.form['email']).first()

        if user == None:
            user = wks.find(request.form['email'], in_column=5)
            if user is not None:
                user = wks.row_values(user.row)
            # user = member_roster.query.filter_by(secondary_email=request.form['email']).first()

        # if the email entered is neither a primary nor secondary in the db, throw error message
        if user == None:
            return render_template("instructions_sent.html")

        # the verification status of the user's primary and secondary emails.
        verif1 = user[5]
        verif2 = user[6]

        # user_object = member_roster(id=user[0],
        #                     first_name=user[1],
        #                     last_name=user[2],
        #                     primary_email=user[3],
        #                     secondary_email=user[4],
        #                     primary_email_status=user[5],
        #                     secondary_email_status=user[6],
        #                     info_completed=user[7],
        #                     organization=user[8],
        #                     phonenumber=user[9],
        #                     titlerole=user[10]
        #                     )

        # login_user(user_object, remember=True, duration=timedelta(weeks=1))

        if verif1 == 'N' and verif2 == 'Y':
            # send an update link to the secondary and a verification link to primary
            p_token = generate_token(user[3])
            confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", confirm_url=confirm_url)
            p_subject = "ISSNAF - Confirm Your Email Address"

            s_token = generate_token(user[4])
            update_url = url_for("update.update_info", token=s_token, _external=True)
            s_html = render_template("update_email.html", update_url=update_url)
            s_subject = "ISSNAF - Link to Update Your Information"

            send_email(user[3], p_subject, p_html)
            send_email(user[4], s_subject, s_html)

            return render_template("instructions_sent.html")

        if verif1 == 'Y'and verif2 == 'N':
            # send an update link to primary and verification to secondary
            p_token = generate_token(user[3])
            update_url = url_for("update.update_info", token=p_token, _external=True)
            p_html = render_template("update_email.html", update_url=update_url)
            p_subject = "ISSNAF - Link to Update Your Information"

            token = generate_token(user[4])
            confirm_url = url_for("registration.confirm_secondary", token=token, _external=True)
            s_html = render_template("verify.html", confirm_url=confirm_url)
            s_subject = "ISSNAF - Confirm Your Email Address"

            send_email(user[3], p_subject, p_html)
            send_email(user[4], s_subject, s_html)

            return render_template("instructions_sent.html")

        if verif1 == 'N' and verif2 == 'N':
            # user is in db, but not verified. send them links to verify both.
            p_token = generate_token(user[3])
            p_confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", confirm_url=p_confirm_url)

            s_token = generate_token(user[4])
            s_confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            s_html = render_template("verify.html", confirm_url=s_confirm_url)

            subject = "ISSNAF - Confirm Your Email Address"
            send_email(user[3], subject, p_html)
            send_email(user[4], subject, s_html)

            return render_template("instructions_sent.html")

        if not current_user.info_completed:
            token = generate_token(user[3])
            subject = "ISSNAF - Complete Your Registration"
            info_url = url_for("registration.info", token=token, _external=True)
            html = render_template("need_info.html", info_url=info_url)

            send_email(user[3], subject, html)

            return render_template("instructions_sent.html")

        else:
            token = generate_token(user[3])
            subject = "ISSNAF - Link to Update Your Information"
            update_url = url_for("update.update_info", token=token, _external=True)
            html = render_template("update_email.html", update_url=update_url)

            send_email(user[3], subject, html)
            send_email(user[4], subject, html)

            return render_template("instructions_sent.html")

    else:
        return render_template("enter_email.html", form=form)
    

@update_blueprint.route('/enter_update/<token>', methods=['GET', 'POST'])
def update_info(token):
    email = confirm_token(token, expiration=1000000)
    
    user = wks.find(email, in_column=4)
    if user is not None:
            user = wks.row_values(user.row)
    # user = member_roster.query.filter_by(primary_email=email).first()
    if user == None:
        user = wks.find(email, in_column=5)
        if user is not None:
            user = wks.row_values(user.row)
    # user = member_roster.query.filter_by(secondary_email=email).first()

    # data = member_data.query.filter_by(user_key=user[0]).first()
    
    form = UpdateForm(request.form, 
                         first_name = user[1],
                         last_name = user[2],
                         primary_email = user[3],
                         secondary_email = user[4],
                         organization = user[8],
                         phonenumber = user[9],
                         titlerole = user[10])

    if user[11] == 'FALSE':                    
        form.primary_subscribe.data = 0
    else:
        form.primary_subscribe.data = 1
    
    if user[12] == 'FALSE':                    
        form.secondary_subscribe.data = 0
    else:
        form.secondary_subscribe.data = 1
                        
    # form.populate_obj(current_user)

    if request.method == 'POST' and form.validate():
        cell_find = wks.find(email)
        cell_row_find = cell_find.row
        
        need_verif = False
        skip = False
        error = False
        subject = "ISSNAF - Confirm Your Email Address"
        user_prim1 = wks.find(request.form['primary_email'], in_column=4)
        user_prim2 = wks.find(request.form['primary_email'], in_column=5)
        user_sec1 = wks.find(request.form['secondary_email'], in_column=4)
        user_sec2 = wks.find(request.form['secondary_email'], in_column=5)
    
        if (user_prim1 is not None or user_prim2 is not None or user_sec1 is not None or user_sec2 is not None):
            error = True

        if user[3] == request.form['primary_email'] or user[3] == request.form['secondary_email'] or user[4] == request.form['primary_email'] or user[4] == request.form['secondary_email']:
            error = False

        if error:
            return render_template("error.html")

        if user[3] == form.secondary_email.data and user[4] == form.primary_email.data:
            skip = True

        if user[3] != form.primary_email.data and not skip:
            need_verif = True

            p_token = generate_token(form.primary_email.data)
            confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            html = render_template("verify.html", confirm_url=confirm_url)

            wks.update_cell(cell_row_find, 6, "N")
            send_email(form.primary_email.data, subject, html)

        if user[4] != form.secondary_email.data and not skip:
            need_verif = True

            s_token = generate_token(form.secondary_email.data)
            confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            html = render_template("verify.html", confirm_url=confirm_url)

            wks.update_cell(cell_row_find, 7, "N")
            send_email(form.secondary_email.data, subject, html)

        if user[5] == "Y":
            wks.update_cell(cell_row_find, 12, form.primary_subscribe.data)
        else:
            


        wks.update_cell(cell_row_find, 2, form.first_name.data)
        wks.update_cell(cell_row_find, 3, form.last_name.data)
        wks.update_cell(cell_row_find, 4, form.primary_email.data)
        wks.update_cell(cell_row_find, 5, form.secondary_email.data)
        wks.update_cell(cell_row_find, 9, form.organization.data)
        wks.update_cell(cell_row_find, 10, form.phonenumber.data)
        wks.update_cell(cell_row_find, 11, form.titlerole.data)

        
        wks.update_cell(cell_row_find, 12, form.primary_subscribe.data)
        wks.update_cell(cell_row_find, 13, form.secondary_subscribe.data)

        if need_verif:
            return render_template("need_verif.html")
        else:
            return render_template("thanks_update.html")

    else:
        return render_template("update_page.html", form=form, token=token)
