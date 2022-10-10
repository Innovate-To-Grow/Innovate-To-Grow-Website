from multiprocessing import Process
from datetime import date
from flask import Blueprint, render_template, url_for, request, redirect
from project import wks
from project.models import current_form
from project.util.email import send_email, delete_email
from project.util.token import confirm_token_no_expiry, generate_token, confirm_token
from project.registration.forms import RegistrationForm, InformationForm

registration_blueprint = Blueprint("registration", __name__, template_folder='templates', static_folder='static')

@registration_blueprint.route("/register", methods=["GET", "POST"])
def register():
    form = RegistrationForm(request.form)

    if request.method == 'POST' and form.validate():
        user_prim1 = wks.find(request.form['primary_email'], in_column=6)
        if user_prim1 is not None:
            row_prim1 = user_prim1.row
            user_prim1 = wks.row_values(row_prim1)
            
        user_prim2 = wks.find(request.form['primary_email'], in_column=7)
        if user_prim2 is not None:
            row_prim2 = user_prim2.row
            user_prim2 = wks.row_values(row_prim2)
            
        user_sec1 = wks.find(request.form['secondary_email'], in_column=6)
        if user_sec1 is not None:
            row_sec1 = user_sec1.row
            user_sec1 = wks.row_values(row_sec1)
            
        user_sec2 = wks.find(request.form['secondary_email'], in_column=7)
        if user_sec2 is not None:
            row_sec2 = user_sec2.row
            user_sec2 = wks.row_values(row_sec2)
        
        if user_prim1 != None or user_prim2 != None or user_sec1 != None or user_sec2 != None:
            complete_subject = "i2G - Complete Your Registration"
            update_subject = "i2G - Link to Update Your Information"
            
            if user_prim1 != None or user_prim2 != None:

                if user_prim1 != None:
                    token = generate_token(user_prim1[5])

                    if user_prim1[7] == "FALSE":
                        process = Process(target=delete_email, args=(30, row_prim1, 6, user_prim1[5]))
                        process.start()
                        
                    if user_prim1[7] == "TRUE" and user_prim1[9] == "FALSE":
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", first=user_prim1[1], last=user_prim1[2], info_url=complete_url)
                        send_email(user_prim1[5], complete_subject, complete_html)

                    elif user_prim1[7] == "TRUE" and user_prim1[9] == "TRUE":
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", first=user_prim1[1], last=user_prim1[2], update_url=update_url)
                        send_email(user_prim1[5], update_subject, update_html)
                
                if user_prim2 != None:
                    token = generate_token(user_prim2[6])

                    if user_prim2[8] == "FALSE": 
                        process = Process(target=delete_email, args=(30, row_prim2, 7, user_prim2[6]))
                        process.start()
                    
                    if user_prim2[8] == "TRUE" and user_prim2[9] == "FALSE":
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", first=user_prim2[1], last=user_prim2[2], info_url=complete_url)
                        send_email(user_prim2[6], complete_subject, complete_html)

                    elif user_prim2[8] == "TRUE" and user_prim2[9] == "TRUE":
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", first=user_prim2[1], last=user_prim2[2], update_url=update_url)
                        send_email(user_prim2[6], update_subject, update_html)

                
            if user_sec1 != None or user_sec2 != None:
                
                if user_sec1 != None:
                    token = generate_token(user_sec1[5])

                    if user_sec1[7] == 'FALSE':
                        process = Process(target=delete_email, args=(30, row_sec1, 6, user_sec1[5]))
                        process.start()
                      
                    if user_sec1[7] == 'TRUE' and user_sec1[9] == 'FALSE':
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", first=user_sec1[1], last=user_sec1[2], info_url=complete_url)
                        send_email(user_sec1[5], complete_subject, complete_html)

                    elif user_sec1[7] == 'TRUE' and user_sec1[9] == 'TRUE':
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", first=user_sec1[1], last=user_sec1[2], update_url=update_url)
                        send_email(user_sec1[5], update_subject, update_html)

                if user_sec2 != None:
                    token = generate_token(user_sec2[6])
                    
                    if user_sec2[8] == "FALSE":
                        process = Process(target=delete_email, args=(30, row_sec2, 7, user_sec2[6]))
                        process.start()
     
                    if user_sec2[8] == "TRUE" and user_sec2[9] == "FALSE":
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", first=user_sec2[1], last=user_sec2[2], info_url=complete_url)
                        send_email(user_sec2[6], complete_subject, complete_html)

                    elif user_sec2[8] == "TRUE" and user_sec2[9] == "TRUE":
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", first=user_sec2[1], last=user_sec2[2], update_url=update_url)
                        send_email(user_sec2[6], update_subject, update_html)
                
            return render_template("error.html")


        else:
            user = [
                len(wks.col_values(1)), # Order
                form.first_name.data, # First Name
                form.last_name.data, # Last Name
                str(date.today()), # When Started
                "",                # Date Updated
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
            p_confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", first=user[1], last=user[2], confirm_url=p_confirm_url)

            s_token = generate_token(user[6])
            s_confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            s_html = render_template("verify.html", first=user[1], last=user[2], confirm_url=s_confirm_url)

            verif_subject = "i2G - Confirm Your Email Address"
            
            send_email(user[5], verif_subject, p_html)
            send_email(user[6], verif_subject, s_html)

            return render_template("instructions_sent.html")

    else:
        return render_template("register.html", form=form)


@registration_blueprint.route('/confirm<token>p')
def confirm_primary(token):
    user = None
    email = confirm_token(token)
    
    if email:
        user = wks.row_values(wks.find(email, in_column=6).row)

    if user == None:
        return render_template("resend_p.html", token=token, _external=True)

    elif user[7] == "TRUE" and user[9] == "TRUE":
        return render_template("already_confirmed.html")

    else:
        cell_find = wks.find(email)
        cell_row_find = cell_find.row
        wks.update_cell(cell_row_find, 8, "TRUE")
        wks.update_cell(cell_row_find, 11, "TRUE")

        if user[9] == "FALSE":
            i_token = generate_token(user[5])
            return redirect(url_for("registration.info", token=i_token, _external=True))

        else:
            return render_template("thanks_confirming.html")
        

@registration_blueprint.route('/confirm<token>s')
def confirm_secondary(token):
    user = None
    email = confirm_token(token)
    
    if email:
        user = wks.row_values(wks.find(email, in_column=7).row)

    if user == None:
        return render_template("resend_s.html", token=token, _external=True)

    elif user[8] == "TRUE" and user[9] == "TRUE":
        return render_template("already_confirmed.html")
        
    else:
        cell_find = wks.find(email)
        cell_row_find = cell_find.row
        wks.update_cell(cell_row_find, 9, "TRUE")
        wks.update_cell(cell_row_find, 12, "TRUE")

        if user[9] == "FALSE":
            i_token = generate_token(user[6])
            return redirect(url_for("registration.info", token=i_token, _external=True))

        else:
            return render_template("thanks_confirming.html")


@registration_blueprint.route('/resend<token>p')
def resend_primary(token):
    email = confirm_token_no_expiry(token)
    if email: user = wks.row_values(wks.find(email, in_column=6).row)
    new_token = generate_token(email)
    confirm_url = url_for('registration.confirm_primary', token=new_token, _external=True)
    html = render_template('verify.html', first=user[1], last=user[2], confirm_url=confirm_url)
    subject = "i2G - Confirm Your Email Address"
    send_email(email, subject, html)
    return render_template("homepage.html")


@registration_blueprint.route('/resend<token>s')
def resend_secondary(token):
    email = confirm_token_no_expiry(token)
    if email: user = wks.row_values(wks.find(email, in_column=7).row)
    new_token = generate_token(email)
    confirm_url = url_for('registration.confirm_secondary', token=new_token, _external=True)
    html = render_template('verify.html', first=user[1], last=user[2], confirm_url=confirm_url)
    subject = "i2G - Confirm Your Email Address"
    send_email(email, subject, html)
    return render_template("homepage.html")


@registration_blueprint.route('/info/<token>', methods=['GET', 'POST'])
def info(token):
    form = InformationForm(request.form)

    email = confirm_token_no_expiry(token)
    user = wks.find(email, in_column=6)
    if user is not None:
            user = wks.row_values(user.row)
    if user == None:
        user = wks.find(email, in_column=7)
        if user is not None:
            user = wks.row_values(user.row)

    if request.method == 'POST' and form.validate():
        if user[9] == "TRUE":
            return render_template("homepage.html")

        cell_find = wks.find(email)
        cell_row_find = cell_find.row

        wks.update_cell(cell_row_find, 13, form.titlerole.data)
        wks.update_cell(cell_row_find, 14, form.organization.data)
        wks.update_cell(cell_row_find, 15, form.phonenumber.data)

        wks.update_cell(cell_row_find, 10, "TRUE")
    
        return render_template("thanks_registering.html")

    else:
        return render_template("information.html", form=form, token=token)
    



from project.util.field import get_field
from wtforms import Form, SubmitField

@registration_blueprint.route('/test', methods=['GET', 'POST'])
def test_view():
    class TestForm(Form): pass

    for row in current_form.query.all():
        setattr(TestForm, row.label, get_field(row))

    setattr(TestForm, "Submit", SubmitField("Submit"))

    form = TestForm()

    return render_template("customform.html", form=form)
