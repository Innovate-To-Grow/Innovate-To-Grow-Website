from calendar import month, week
from datetime import datetime, timedelta
from random import randint
from flask import Blueprint, render_template, url_for, request, redirect
from flask_login import login_required, login_user, current_user, logout_user
from project.models import member_roster
from project.util.email import send_email
from project.util.token import generate_token, confirm_token
from project.registration.forms import RegistrationForm, InformationForm
# Google Sheet
import gspread
sa = gspread.service_account(filename="service_account.json")
sh = sa.open("I2G-Master-People")
wks = sh.worksheet("double-email-test")

registration_blueprint = Blueprint("registration", __name__, template_folder='templates',static_folder='static')

@registration_blueprint.route("/register", methods=["GET", "POST"])
def register(): 
    form = RegistrationForm(request.form)

    if request.method == 'POST' and form.validate():

        verif_subject = "ISSNAF - Confirm Your Email Address"

        user_prim1 = wks.find(request.form['primary_email'], in_column=4)
        if user_prim1 is not None:
            user_prim1 = wks.row_values(user_prim1.row)
            
        user_prim2 = wks.find(request.form['primary_email'], in_column=5)
        if user_prim2 is not None:
            user_prim2 = wks.row_values(user_prim2.row)
            
        user_sec1 = wks.find(request.form['secondary_email'], in_column=4)
        if user_sec1 is not None:
            user_sec1 = wks.row_values(user_sec1.row)
            
        user_sec2 = wks.find(request.form['secondary_email'], in_column=5)
        if user_sec2 is not None:
            user_sec2 = wks.row_values(user_sec2.row)
        
        if user_prim1 != None or user_prim2 != None or user_sec1 != None or user_sec2 != None:
            update_subject = "ISSNAF - Link to Update Your Information"
            complete_subject = "ISSNAF - Complete Your Registration"
        
            if user_prim1 != None or user_prim2 != None:

                if user_prim1 != None:
                    token = generate_token(user_prim1[3])

                    user = member_roster(id=user_prim1[0],
                                        first_name=user_prim1[1],
                                        last_name=user_prim1[2],
                                        primary_email=user_prim1[3],
                                        secondary_email=user_prim1[4],
                                        primary_email_status=user_prim1[5],
                                        secondary_email_status=user_prim1[6],
                                        info_completed=user_prim1[7],
                                        primary_subscribe = user_prim1[11],
                                        secondary_subscribe = user_prim1[12])

                    login_user(user, remember=True, duration=timedelta(weeks=1))

                    if user_prim1[5] == "N":
                        confirm_url = url_for("registration.confirm_primary", token=token, _external=True)
                        html = render_template("verify.html", confirm_url=confirm_url)
                        send_email(user_prim1[3], verif_subject, html)
                        
                    elif user_prim1[5] == "Y" and user_prim1[7] == "N":
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", info_url=complete_url)
                        send_email(user_prim1[3], complete_subject, complete_html)

                    elif user_prim1[5] == "Y" and user_prim1[7] == "Y":
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", update_url=update_url)
                        send_email(user_prim1[3], update_subject, update_html)
                
                if user_prim2 != None:
                    token = generate_token(user_prim2[4])

                    user = member_roster(id=user_prim2[0],
                                        first_name=user_prim2[1],
                                        last_name=user_prim2[2],
                                        primary_email=user_prim2[3],
                                        secondary_email=user_prim2[4],
                                        primary_email_status=user_prim2[5],
                                        secondary_email_status=user_prim2[6],
                                        info_completed=user_prim2[7],
                                        primary_subscribe = user_prim2[11],
                                        secondary_subscribe = user_prim2[12])

                    login_user(user, remember=True, duration=timedelta(weeks=1))

                    if user_prim2[6] == "N":
                        confirm_url = url_for("registration.confirm_secondary", token=token, _external=True)
                        html = render_template("verify.html", confirm_url=confirm_url)
                        send_email(user_prim2[4], verif_subject, html)
                        
                    elif user_prim2[6] == "Y" and user_prim2[7] == "N":
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", info_url=complete_url)
                        send_email(user_prim2[4], complete_subject, complete_html)

                    elif user_prim2[6] == "Y" and user_prim2[7] == "Y":
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", update_url=update_url)
                        send_email(user_prim2[4], update_subject, update_html)

                
            if user_sec1 != None or user_sec2 != None:
                
                if user_sec1 != None:
                    token = generate_token(user_sec1[3])

                    user = member_roster(id=user_sec1[0],
                                        first_name=user_sec1[1],
                                        last_name=user_sec1[2],
                                        primary_email=user_sec1[3],
                                        secondary_email=user_sec1[4],
                                        primary_email_status=user_sec1[5],
                                        secondary_email_status=user_sec1[6],
                                        info_completed=user_sec1[7],
                                        primary_subscribe = user_sec1[11],
                                        secondary_subscribe = user_sec1[12])

                    login_user(user_sec1, remember=True, duration=timedelta(weeks=1))

                    if user_sec1[5] == 'N':
                        token = generate_token(user_sec1[3])
                        confirm_url = url_for("registration.confirm_primary", token=token, _external=True)
                        html = render_template("verify.html", confirm_url=confirm_url)
                        send_email(user_sec1[3], verif_subject, html)
                    
                    elif user_sec1[5] == 'Y' and user_sec1[7] == 'N':
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", info_url=complete_url)
                        send_email(user_sec1[3], complete_subject, complete_html)

                    elif user_sec1[5] == 'Y' and user_sec1[7] == 'Y':
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", update_url=update_url)
                        send_email(user_sec1[3], update_subject, update_html)

                if user_sec2 != None:
                    token = generate_token(user_sec2[4])
                    
                    user = member_roster(id=user_sec2[0],
                                        first_name=user_sec2[1],
                                        last_name=user_sec2[2],
                                        primary_email=user_sec2[3],
                                        secondary_email=user_sec2[4],
                                        primary_email_status=user_sec2[5],
                                        secondary_email_status=user_sec2[6],
                                        info_completed=user_sec2[7],
                                        primary_subscribe = user_sec2[11],
                                        secondary_subscribe = user_sec2[12])
                    
                    login_user(user_sec2, remember=True, duration=timedelta(weeks=1))

                    if user_sec2[6] == "N":
                        token = generate_token(user_sec2[4])
                        confirm_url = url_for("registration.confirm_secondary", token=token, _external=True)
                        html = render_template("verify.html", confirm_url=confirm_url)
                        send_email(user_sec2[4], verif_subject, html)
                    
                    elif user_sec2[6] == "Y" and user_sec2[7] == "N":
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", info_url=complete_url)
                        send_email(user_sec2[4], complete_subject, complete_html)

                    elif user_sec2[6] == "Y" and user_sec2[7] == "Y":
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", update_url=update_url)
                        send_email(user_sec2[4], update_subject, update_html)
                
            return render_template("instructions_sent.html")


        else:
            user = member_roster(id = len(wks.col_values(1)),
                                first_name = form.first_name.data,
                                last_name = form.last_name.data,
                                primary_email = form.primary_email.data,
                                secondary_email = form.secondary_email.data,
                                primary_email_status = "N",
                                secondary_email_status = "N",
                                info_completed = "N",
                                primary_subscribe = "FALSE",
                                secondary_subscribe = "FALSE")

            user_row = [user.id, user.first_name, user.last_name, user.primary_email,
                        user.secondary_email, user.primary_email_status, user.secondary_email_status,
                        user.info_completed, "","","", user.primary_subscribe, user.secondary_subscribe]

            wks.append_row(user_row)

            login_user(user, remember=True, duration=timedelta(weeks=1))

            p_token = generate_token(user.primary_email)
            p_confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", confirm_url=p_confirm_url)

            s_token = generate_token(user.secondary_email)
            s_confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            s_html = render_template("verify.html", confirm_url=s_confirm_url)

            verif_subject = "ISSNAF - Confirm Your Email Address"
            
            send_email(user.primary_email, verif_subject, p_html)
            send_email(user.secondary_email, verif_subject, s_html)

            return render_template("instructions_sent.html")

    else:
        return render_template("register.html", form=form)


@registration_blueprint.route('/confirm_p/<token>')
def confirm_primary(token):
    if current_user.primary_email_status != "N" and current_user.info_completed != "N":
        return render_template("already_confirmed.html")

    email = confirm_token(token)
    user = None

    if email:
        user = wks.row_values(wks.find(email, in_column=4).row)

    if user == None:
        return render_template("resend_p.html")
    else:
        current_user.primary_email_status = "Y"

        cell_find = wks.find(email)
        cell_row_find = cell_find.row
        wks.update_cell(cell_row_find, 6, "Y")
        wks.update_cell(cell_row_find, 12, "TRUE")

        if user[7] == 'N':
            i_token = generate_token(user[4])
            return redirect(url_for("registration.info", token=i_token, _external=True))
        else:
            return render_template("thanks_confirming.html")
        

@registration_blueprint.route('/confirm_s/<token>')
def confirm_secondary(token):
    if current_user.secondary_email_status != "N" and current_user.info_completed != "N":
        return render_template("already_confirmed.html")

    email = confirm_token(token)
    user = None

    if email:
        user = wks.row_values(wks.find(email, in_column=5).row)

    if user == None:
        return render_template("resend_s.html")
    else:
        current_user.secondary_email_status = "Y"

        cell_find = wks.find(email)
        cell_row_find = cell_find.row
        wks.update_cell(cell_row_find, 7, "Y")
        wks.update_cell(cell_row_find, 13, "TRUE")

        if user[7] == 'N':
            i_token = generate_token(user[4])
            return redirect(url_for("registration.info", token=i_token, _external=True))
        else:
            return render_template("thanks_confirming.html")


@registration_blueprint.route('/resend_p')
def resend_primary():
    token = generate_token(current_user.primary_email)
    confirm_url = url_for('registration.confirm_primary', token=token, _external=True)
    html = render_template('verify.html', confirm_url=confirm_url)
    subject = "ISSNAF - Confirm Your Email Address"
    send_email(current_user.primary_email, subject, html)
    return render_template("homepage.html")


@registration_blueprint.route('/resend_s')
def resend_secondary():
    token = generate_token(current_user.secondary_email)
    confirm_url = url_for('registration.confirm_secondary', token=token, _external=True)
    html = render_template('verify.html', confirm_url=confirm_url)
    subject = "ISSNAF - Confirm Your Email Address"
    send_email(current_user.secondary_email, subject, html)
    return render_template("homepage.html")


@registration_blueprint.route('/info/<token>', methods=['GET', 'POST'])
def info(token):
    form = InformationForm(request.form)

    email = confirm_token(token, expiration=1000000)
    user = wks.find(email, in_column=4)
    if user is not None:
            user = wks.row_values(user.row)
    if user == None:
        user = wks.find(email, in_column=5)
        if user is not None:
            user = wks.row_values(user.row)

    if request.method == 'POST' and form.validate():
        if user[7] != "N":
            return render_template("homepage.html")

        current_user.organization = form.organization.data
        current_user.phonenumber = form.phonenumber.data
        current_user.titlerole = form.titlerole.data

        cell_find = wks.find(email)
        cell_row_find = cell_find.row

        wks.update_cell(cell_row_find, 9, current_user.organization)
        wks.update_cell(cell_row_find, 10, current_user.phonenumber)
        wks.update_cell(cell_row_find, 11, current_user.titlerole)

        current_user.info_completed = "Y"
        wks.update_cell(cell_row_find, 8, current_user.info_completed)
    
        return render_template("thanks_registering.html")

    else:
        return render_template("information.html", form=form, token=token)
    
    