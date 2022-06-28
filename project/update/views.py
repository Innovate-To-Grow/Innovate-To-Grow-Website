from datetime import timedelta

from project.update.forms import EmailForm, UpdateForm
from flask import Blueprint, render_template, url_for, request
from flask_login import login_required, login_user, current_user
from project.models import member_roster
from project import db
from project.util.email import send_email
from project.util.token import confirm_token, generate_token

update_blueprint = Blueprint("update", __name__, template_folder='templates',static_folder='static')

# check the database to see if the input email has a user with a registered prim. or secon. email
@update_blueprint.route('/update', methods=['GET', 'POST'])
def enter_email():
    form = EmailForm(request.form)

    if request.method == 'POST' and form.validate():
        user = member_roster.query.filter_by(primary_email=request.form['email']).first()

        if user == None:
            user = member_roster.query.filter_by(secondary_email=request.form['email']).first()

        # if the email entered is neither a primary nor secondary in the db, throw error message
        if user == None:
            return render_template("instructions_sent.html")

        # the verification status of the user's primary and secondary emails.
        verif1 = user.primary_email_status
        verif2 = user.secondary_email_status

        login_user(user, remember=True, duration=timedelta(weeks=1))

        if not verif1 and verif2:
            # send an update link to the secondary and a verification link to primary
            p_token = generate_token(user.primary_email)
            confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", confirm_url=confirm_url)
            p_subject = "ISSNAF - Confirm Your Email Address"

            s_token = generate_token(user.secondary_email)
            update_url = url_for("update.update_info", token=s_token, _external=True)
            s_html = render_template("update_email.html", update_url=update_url)
            s_subject = "ISSNAF - Link to Update Your Information"

            send_email(user.primary_email, p_subject, p_html)
            send_email(user.secondary_email, s_subject, s_html)

            return render_template("instructions_sent.html")

        if verif1 and not verif2:
            # send an update link to primary and verification to secondary
            p_token = generate_token(user.primary_email)
            update_url = url_for("update.update_info", token=p_token, _external=True)
            p_html = render_template("update_email.html", update_url=update_url)
            p_subject = "ISSNAF - Link to Update Your Information"

            token = generate_token(user.secondary_email)
            confirm_url = url_for("registration.confirm_secondary", token=token, _external=True)
            s_html = render_template("verify.html", confirm_url=confirm_url)
            s_subject = "ISSNAF - Confirm Your Email Address"

            send_email(user.primary_email, p_subject, p_html)
            send_email(user.secondary_email, s_subject, s_html)

            return render_template("instructions_sent.html")

        if not verif1 and not verif2:
            # user is in db, but not verified. send them links to verify both.
            p_token = generate_token(user.primary_email)
            p_confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", confirm_url=p_confirm_url)

            s_token = generate_token(user.secondary_email)
            s_confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            s_html = render_template("verify.html", confirm_url=s_confirm_url)

            subject = "ISSNAF - Confirm Your Email Address"
            send_email(user.primary_email, subject, p_html)
            send_email(user.secondary_email, subject, s_html)

            return render_template("instructions_sent.html")

        if not current_user.info_completed:
            token = generate_token(user.primary_email)
            subject = "ISSNAF - Complete Your Registration"
            info_url = url_for("registration.info", token=token, _external=True)
            html = render_template("need_info.html", info_url=info_url)

            send_email(current_user.primary_email, subject, html)

            return render_template("instructions_sent.html")

        else:
            token = generate_token(user.primary_email)
            subject = "ISSNAF - Link to Update Your Information"
            update_url = url_for("update.update_info", token=token, _external=True)
            html = render_template("update_email.html", update_url=update_url)

            send_email(user.primary_email, subject, html)
            send_email(user.secondary_email, subject, html)

            return render_template("instructions_sent.html")

    else:
        return render_template("enter_email.html", form=form)
    

@update_blueprint.route('/enter_update/<token>', methods=['GET', 'POST'])
@login_required
def update_info(token):
    email = confirm_token(token, expiration=1000000)
    user = member_roster.query.filter_by(primary_email=email).first()
    if user == None:
        user = member_roster.query.filter_by(secondary_email=email).first()

    data = member_data.query.filter_by(user_key=user.user_key).first()
    form = UpdateForm(request.form, obj=data,
                        first_name=user.first_name, 
                        last_name=user.last_name,
                        primary_email=user.primary_email,
                        secondary_email=user.secondary_email,
                        zipcode=data.zip_code,
                        country=data.country,
                        country_other=data.country_other,
                        organization=data.organization,
                        school=data.school,
                        division=data.department,
                        position=data.position,
                        discipline=data.discipline,
                        discipline_other=data.discipline_other,
                        specialty=data.specialty,
                        education=data.highest_degree,
                        education_other=data.highest_degree_other,
                        education_year=data.graduation_date,
                        alma_mater=data.alma_mater,
                        alma_mater_italy=data.alma_mater_italy,
                        linkedin=data.linked_in,
                        researchgate=data.research_gate,
                        webpage=data.webpage,
                        comment=data.comments,
                        affiliation=data.member_type)


    if request.method == 'POST' and form.validate():
        form.populate_obj(data)

        user.first_name = form.first_name.data
        user.last_name = form.last_name.data
        
        need_verif = False
        skip = False
        subject = "ISSNAF - Confirm Your Email Address"

        if user.primary_email == form.secondary_email.data and user.secondary_email == form.primary_email.data:
            skip = True

        if user.primary_email != form.primary_email.data and not skip:
            need_verif = True

            p_token = generate_token(form.primary_email.data)
            confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            html = render_template("verify.html", confirm_url=confirm_url)

            user.primary_email_status = False
            send_email(form.primary_email.data, subject, html)

        if user.secondary_email != form.secondary_email.data and not skip:
            need_verif = True

            s_token = generate_token(form.secondary_email.data)
            confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            html = render_template("verify.html", confirm_url=confirm_url)

            user.secondary_email_status = False
            send_email(form.secondary_email.data, subject, html)


        user.primary_email = form.primary_email.data
        user.secondary_email = form.secondary_email.data

        data.city = form.city.data
        data.state = form.state.data
        data.zip_code = form.zipcode.data
        data.country = form.country.data
        data.country_other = form.country_other.data
        data.organization = form.organization.data
        data.school = form.school.data
        data.department = form.division.data
        data.position = form.position.data
        data.discipline = form.discipline.data
        data.discipline_other = form.discipline_other.data
        data.specialty = form.specialty.data
        data.highest_degree = form.education.data
        data.highest_degree_other = form.education_other.data
        data.graduation_date = form.education_year.data
        data.alma_mater = form.alma_mater.data
        data.alma_mater_italy = form.alma_mater_italy.data
        data.linked_in = form.linkedin.data
        data.research_gate = form.researchgate.data
        data.webpage = form.webpage.data
        data.comments = form.comments.data
        data.member_type = form.affiliation.data

        db.session.commit()

        if need_verif:
            return render_template("need_verif.html")
        else:
            return render_template("thanks_update.html")

    else:
        return render_template("update_page.html", form=form, token=token)
