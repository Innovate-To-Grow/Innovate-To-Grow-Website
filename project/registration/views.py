from calendar import month, week
from datetime import datetime, timedelta
from random import randint
from flask import Blueprint, render_template, url_for, request, redirect
from flask_login import login_required, login_user, current_user, logout_user
from project import db
from project.models import member_roster, member_data
from project.util.email import send_email
from project.util.token import generate_token, confirm_token
from project.registration.forms import RegistrationForm, InformationForm

registration_blueprint = Blueprint("registration", __name__, template_folder='templates',static_folder='static')

@registration_blueprint.route("/register", methods=["GET", "POST"])
def register(): 
    form = RegistrationForm(request.form)

    if request.method == 'POST' and form.validate():
        verif_subject = "ISSNAF - Confirm Your Email Address"

        user_prim1 = member_roster.query.filter_by(primary_email=request.form['primary_email']).first()
        user_prim2 = member_roster.query.filter_by(secondary_email=request.form['primary_email']).first()
        user_sec1 = member_roster.query.filter_by(primary_email=request.form['secondary_email']).first()
        user_sec2 = member_roster.query.filter_by(secondary_email=request.form['secondary_email']).first()
        
        if user_prim1 != None or user_prim2 != None or user_sec1 != None or user_sec2 != None:
            update_subject = "ISSNAF - Link to Update Your Information"
            complete_subject = "ISSNAF - Complete Your Registration"
            
            if user_prim1 != None or user_prim2 != None:

                if user_prim1 != None:
                    token = generate_token(user_prim1.primary_email)
                    login_user(user_prim1, remember=True, duration=timedelta(weeks=1))

                    if not user_prim1.primary_email_status:
                        confirm_url = url_for("registration.confirm_primary", token=token, _external=True)
                        html = render_template("verify.html", confirm_url=confirm_url)
                        send_email(user_prim1.primary_email, verif_subject, html)
                        
                    elif user_prim1.primary_email_status and not user_prim1.info_completed:
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", info_url=complete_url)
                        send_email(user_prim1.primary_email, complete_subject, complete_html)

                    elif user_prim1.primary_email_status and user_prim1.info_completed:
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", update_url=update_url)
                        send_email(user_prim1.primary_email, update_subject, update_html)
                
                if user_prim2 != None:
                    token = generate_token(user_prim2.secondary_email)
                    login_user(user_prim2, remember=True, duration=timedelta(weeks=1))

                    if not user_prim2.secondary_email_status:
                        confirm_url = url_for("registration.confirm_secondary", token=token, _external=True)
                        html = render_template("verify.html", confirm_url=confirm_url)
                        send_email(user_prim2.secondary_email, verif_subject, html)
                        
                    elif user_prim2.secondary_email_status and not user_prim2.info_completed:
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", info_url=complete_url)
                        send_email(user_prim2.secondary_email, complete_subject, complete_html)

                    elif user_prim2.secondary_email_status and user_prim2.info_completed:
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", update_url=update_url)
                        send_email(user_prim2.secondary_email, update_subject, update_html)

                
            if user_sec1 != None or user_sec2 != None:
                
                if user_sec1 != None:
                    token = generate_token(user_sec1.primary_email)
                    login_user(user_sec1, remember=True, duration=timedelta(weeks=1))

                    if not user_sec1.primary_email_status:
                        token = generate_token(user_sec1.primary_email)
                        confirm_url = url_for("registration.confirm_primary", token=token, _external=True)
                        html = render_template("verify.html", confirm_url=confirm_url)
                        send_email(user_sec1.primary_email, verif_subject, html)
                    
                    elif user_sec1.primary_email_status and not user_sec1.info_completed:
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", info_url=complete_url)
                        send_email(user_sec1.primary_email, complete_subject, complete_html)

                    elif user_sec1.primary_email_status and user_sec1.info_completed:
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", update_url=update_url)
                        send_email(user_sec1.primary_email, update_subject, update_html)

                if user_sec2 != None:
                    token = generate_token(user_sec2.secondary_email)
                    login_user(user_sec2, remember=True, duration=timedelta(weeks=1))

                    if not user_sec2.secondary_email_status:
                        token = generate_token(user_sec2.secondary_email)
                        confirm_url = url_for("registration.confirm_secondary", token=token, _external=True)
                        html = render_template("verify.html", confirm_url=confirm_url)
                        send_email(user_sec2.secondary_email, verif_subject, html)
                    
                    elif user_sec2.secondary_email_status and not user_sec2.info_completed:
                        complete_url = url_for("registration.info", token=token, _external=True)
                        complete_html = render_template("need_info.html", info_url=complete_url)
                        send_email(user_sec2.secondary_email, complete_subject, complete_html)

                    elif user_sec2.secondary_email_status and user_sec2.info_completed:
                        update_url = url_for("update.update_info", token=token, _external=True)
                        update_html = render_template("update_email.html", update_url=update_url)
                        send_email(user_sec2.secondary_email, update_subject, update_html)
                
            return render_template("instructions_sent.html")


        else:
            user_key = 0
            min_ = 1
            max_ = 1000000000
            user_key = randint(min_, max_)
            find_key = member_roster.query.filter_by(user_key=user_key).first()

            while find_key != None:
                user_key = randint(min_, max_)
                find_key = member_roster.query.filter_by(user_key=user_key).first()

            user = member_roster(user_key=user_key,
                                first_name=form.first_name.data,
                                last_name=form.last_name.data, 
                                primary_email=form.primary_email.data, 
                                primary_email_status=False,
                                secondary_email=form.secondary_email.data,
                                secondary_email_status=False,
                                info_completed=False)

            db.session.add(user)
            db.session.commit()

            login_user(user, remember=True, duration=timedelta(weeks=1))

            p_token = generate_token(user.primary_email)
            p_confirm_url = url_for("registration.confirm_primary", token=p_token, _external=True)
            p_html = render_template("verify.html", confirm_url=p_confirm_url)

            s_token = generate_token(user.secondary_email)
            s_confirm_url = url_for("registration.confirm_secondary", token=s_token, _external=True)
            s_html = render_template("verify.html", confirm_url=s_confirm_url)

            send_email(user.primary_email, verif_subject, p_html)
            send_email(user.secondary_email, verif_subject, s_html)

            return render_template("instructions_sent.html")

    else:
        return render_template("register.html", form=form)


@registration_blueprint.route('/confirm_p/<token>')
@login_required
def confirm_primary(token):
    if current_user.primary_email_status and current_user.info_completed:
        return render_template("already_confirmed.html")

    email = confirm_token(token)
    user = member_roster.query.filter_by(primary_email=email).first()

    if user == None:
        return render_template("resend_p.html")
    else:
        user.primary_email_status = True
        user.primary_time = datetime.now()

        db.session.commit()

        if not user.info_completed:
            i_token = generate_token(user.primary_email)
            return redirect(url_for("registration.info", token=i_token, _external=True))
        else:
            return render_template("thanks_confirming.html")
        

@registration_blueprint.route('/confirm_s/<token>')
@login_required
def confirm_secondary(token):
    if current_user.secondary_email_status and current_user.info_completed:
        return render_template("already_confirmed.html")

    email = confirm_token(token)
    user = member_roster.query.filter_by(secondary_email=email).first()

    if user == None:
        return render_template("resend_s.html")
    else:
        user.secondary_email_status = True
        user.secondary_time = datetime.now()

        db.session.commit()

        if not user.info_completed:
            i_token = generate_token(user.primary_email)
            return redirect(url_for("registration.info", token=i_token, _external=True))
        else:
            return render_template("thanks_confirming.html")


@registration_blueprint.route('/resend_p')
@login_required
def resend_primary():
    token = generate_token(current_user.primary_email)
    confirm_url = url_for('registration.confirm_primary', token=token, _external=True)
    html = render_template('verify.html', confirm_url=confirm_url)
    subject = "ISSNAF - Confirm Your Email Address"
    send_email(current_user.primary_email, subject, html)
    return render_template("homepage.html")


@registration_blueprint.route('/resend_s')
@login_required
def resend_secondary():
    token = generate_token(current_user.secondary_email)
    confirm_url = url_for('registration.confirm_secondary', token=token, _external=True)
    html = render_template('verify.html', confirm_url=confirm_url)
    subject = "ISSNAF - Confirm Your Email Address"
    send_email(current_user.secondary_email, subject, html)
    return render_template("homepage.html")


@registration_blueprint.route('/info/<token>', methods=['GET', 'POST'])
@login_required
def info(token):
    form = InformationForm(request.form)

    email = confirm_token(token, expiration=1000000)
    user = member_roster.query.filter_by(primary_email=email).first()
    if user == None:
        user = member_roster.query.filter_by(secondary_email=email).first()

    if request.method == 'POST' and form.validate():
        if user.info_completed:
            return render_template("homepage.html")

        data = member_data(user_key=user.user_key,
                            city=form.city.data,
                            state=form.state.data,
                            zip_code=form.zipcode.data,
                            country=form.country.data,
                            country_other = form.country_other.data,
                            organization=form.organization.data,
                            school=form.school.data,
                            department=form.division.data,
                            position=form.position.data,
                            discipline=form.discipline.data,
                            discipline_other=form.discipline_other.data,
                            specialty=form.specialty.data,
                            highest_degree=form.education.data,
                            highest_degree_other=form.education_other.data,
                            graduation_date=form.education_year.data,
                            alma_mater=form.alma_mater.data,
                            alma_mater_italy=form.alma_mater_italy.data,
                            linked_in=form.linkedin.data,
                            research_gate=form.researchgate.data,
                            webpage=form.webpage.data,
                            comments=form.comments.data,
                            member_type=form.affiliation.data)

        user.info_completed = True
        
        db.session.add(data)
        db.session.commit()

        return render_template("thanks_registering.html")

    else:
        return render_template("information.html", form=form, token=token)
    
