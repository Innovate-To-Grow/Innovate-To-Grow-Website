from datetime import datetime
from threading import Thread
from gspread.cell import Cell
from flask import Blueprint, render_template, url_for, request
from project import wks
from project.models import edit_form
from project.utils.email import send_email
from project.utils.field import get_field, checkbox_get_choices
from project.utils.token import confirm_token_no_expiry, generate_token
from project.utils.index_helper import wks_indices, arr_indices
from project.utils.threads import expiry_timer
from project.forms.update_forms import EmailForm, UpdateForm

update_blueprint = Blueprint("update", __name__, template_folder="../templates/update")


# check the database to see if the input email has a user with a registered prim. or secon. email
@update_blueprint.route("/update", methods=["GET", "POST"])
def enter_email():
    form = EmailForm()

    wks_idx = wks_indices()
    arr_idx = arr_indices()

    if request.method == "POST" and form.validate():
        email = request.form["email"].lower()

        user = wks.find(email, in_column=wks_idx["Primary Email"])
        if user is not None:
            user = wks.row_values(user.row)
        if user is None:
            user = wks.find(email, in_column=wks_idx["Secondary Email"])
            if user is not None:
                user = wks.row_values(user.row)
            else:
                return render_template("error3.html")

        if (user[arr_idx["Primary Verified"]] == "FALSE" and user[arr_idx["Secondary Verified"]] == "TRUE"):
            # send an update link to the secondary and a verification link to primary
            p_token = generate_token(user[arr_idx["Primary Email"]])
            confirm_url = url_for("registration.confirm", token=p_token, _external=True)
            p_html = render_template(
                "verify_email.html",
                first=user[arr_idx["First Name"]],
                last=user[arr_idx["Last Name"]],
                confirm_url=confirm_url,
            )
            p_subject = "I2G - Confirm Your Email Address"

            s_token = generate_token(user[arr_idx["Secondary Email"]])
            update_url = url_for("update.update_info", token=s_token, _external=True)
            s_html = render_template(
                "update_email.html",
                first=user[arr_idx["First Name"]],
                last=user[arr_idx["Last Name"]],
                update_url=update_url,
            )
            s_subject = "I2G - Link to Update Your Information"

            if user[arr_idx["Primary Email"]] != "":
                send_email(user[arr_idx["Primary Email"]], p_subject, p_html)

            if user[arr_idx["Secondary Email"]] != "":
                send_email(user["Secondary Email"], s_subject, s_html)

        elif (user[arr_idx["Primary Verified"]] == "TRUE" and user[arr_idx["Secondary Verified"]] == "FALSE"):
            # send an update link to primary and verification to secondary
            p_token = generate_token(user[arr_idx["Primary Email"]])
            update_url = url_for("update.update_info", token=p_token, _external=True)
            p_html = render_template(
                "update_email.html",
                first=user[arr_idx["First Name"]],
                last=user[arr_idx["Last Name"]],
                update_url=update_url,
            )
            p_subject = "I2G - Link to Update Your Information"

            s_token = generate_token(user[arr_idx["Secondary Email"]])
            confirm_url = url_for("registration.confirm", token=s_token, _external=True)
            s_html = render_template(
                "verify_email.html",
                first=user[arr_idx["First Name"]],
                last=user[arr_idx["Last Name"]],
                confirm_url=confirm_url,
            )
            s_subject = "I2G - Confirm Your Email Address"

            if user[arr_idx["Primary Email"]] != "":
                send_email(user[arr_idx["Primary Email"]], p_subject, p_html)

            if user[arr_idx["Secondary Email"]] != "":
                send_email(user[arr_idx["Secondary Email"]], s_subject, s_html)

        elif (user[arr_idx["Primary Verified"]] == "FALSE" and user[arr_idx["Secondary Verified"]] == "FALSE"):
            # user is in db, but not verified. send them links to verify both.
            p_token = generate_token(user[arr_idx["Primary Email"]])
            p_confirm_url = url_for("registration.confirm", token=p_token, _external=True)
            p_html = render_template(
                "verify_email.html",
                first=user[arr_idx["First Name"]],
                last=user[arr_idx["Last Name"]],
                confirm_url=p_confirm_url,
            )

            s_token = generate_token(user[arr_idx["Secondary Email"]])
            s_confirm_url = url_for("registration.confirm", token=s_token, _external=True)
            s_html = render_template(
                "verify_email.html",
                first=user[arr_idx["First Name"]],
                last=user[arr_idx["Last Name"]],
                confirm_url=s_confirm_url,
            )

            subject = "I2G - Confirm Your Email Address"

            if user[arr_idx["Primary Email"]] != "":
                send_email(user[arr_idx["Primary Email"]], subject, p_html)

            if user[arr_idx["Secondary Email"]] != "":
                send_email(user[arr_idx["Secondary Email"]], subject, s_html)

        else:
            token = generate_token(form.email.data)
            subject = "I2G - Link to Update Your Information"
            update_url = url_for("update.update_info", token=token, _external=True)
            html = render_template(
                "update_email.html",
                first=user[arr_idx["First Name"]],
                last=user[arr_idx["Last Name"]],
                update_url=update_url,
            )

            if user[arr_idx["Primary Email"]] != "":
                send_email(user[arr_idx["Primary Email"]], subject, html)

            if user[arr_idx["Secondary Email"]] != "":
                send_email(user[arr_idx["Secondary Email"]], subject, html)

        return render_template("instructions_sent.html")

    else:
        return render_template("enter_form.html", form=form)


@update_blueprint.route("/enter_update/<token>", methods=["GET", "POST"])
def update_info(token):
    email = confirm_token_no_expiry(token)

    wks_idx = wks_indices()
    arr_idx = arr_indices()

    if email:
        user = wks.find(email, in_column=wks_idx["Primary Email"])
        if user is not None:
            user = wks.row_values(user.row)
        if user is None:
            user = wks.find(email, in_column=wks_idx["Secondary Email"])
            if user is not None:
                user = wks.row_values(user.row)
            else:
                return render_template("error2.html")
    else:
        return render_template("error2.html")

    for row in edit_form.query.all():
        setattr(UpdateForm, row.label, get_field(row))

    primary_temp = False
    if user[arr_idx["Primary Subscribed"]] == "TRUE":
        primary_temp = True

    secondary_temp = False
    if user[arr_idx["Secondary Subscribed"]] == "TRUE":
        secondary_temp = True

    person = {
        "first_name": user[arr_idx["First Name"]],
        "last_name": user[arr_idx["Last Name"]],
        "primary_email": user[arr_idx["Primary Email"]],
        "secondary_email": user[arr_idx["Secondary Email"]],
        "primary_subscribe": primary_temp,
        "secondary_subscribe": secondary_temp,
    }

    for row in edit_form.query.all():
        if wks_idx[row.label] > len(user):
            person.update([(row.label, "")])
        else:
            if row.field_type == "Checkbox":
                keys = []
                if user[arr_idx[row.label]] != "":
                    choices = checkbox_get_choices(row.options)
                    for val in user[arr_idx[row.label]].split("\n"):
                        key = [key for key, v in choices if v == val][0]
                        keys.append(key)
                person.update([(row.label, keys)])
            else:
                person.update([(row.label, user[arr_idx[row.label]])])

    form = UpdateForm(data=person)

    if request.method == "POST" and form.validate_on_submit():
        cell_find = wks.find(email, in_column=wks_idx["Primary Email"])
        if cell_find is None:
            cell_find = wks.find(email, in_column=wks_idx["Secondary Email"])

        row_find = cell_find.row

        cells = []

        can_update = True

        swap = False
        need_verif = False
        sent_to_prim = False
        sent_to_sec = False

        remove_subject = "I2G - Unverified Email Removed"
        verif_subject = "I2G - Confirm Your Email Address"

        prim_email = request.form["primary_email"].lower()
        sec_email = request.form["secondary_email"].lower()

        user_prim1 = wks.find(prim_email, in_column=wks_idx["Primary Email"])
        if user_prim1 is not None:
            row_prim1 = user_prim1.row
            user_prim1 = wks.row_values(row_prim1)

        user_prim2 = wks.find(prim_email, in_column=wks_idx["Secondary Email"])
        if user_prim2 is not None:
            row_prim2 = user_prim2.row
            user_prim2 = wks.row_values(row_prim2)

        user_sec1 = wks.find(sec_email, in_column=wks_idx["Primary Email"])
        if user_sec1 is not None:
            row_sec1 = user_sec1.row
            user_sec1 = wks.row_values(row_sec1)

        user_sec2 = wks.find(sec_email, in_column=wks_idx["Secondary Email"])
        if user_sec2 is not None:
            row_sec2 = user_sec2.row
            user_sec2 = wks.row_values(row_sec2)

        if user_prim1 is not None and row_prim1 != row_find:
            if user_prim1[arr_idx["Primary Expired"]] == "FALSE":
                can_update = False
            elif user_prim1[arr_idx["Primary Expired"]] == "TRUE":
                cells.append(Cell(row_prim1, wks_idx["Primary Email"], ""))
                if user_prim1[arr_idx["Secondary Email"]] != "" and user_prim1[arr_idx["Secondary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_prim1[arr_idx["First Name"]],
                                           last=user_prim1[arr_idx["Last Name"]],
                                           email=user_prim1[arr_idx["Primary Email"]])
                    send_email(user_prim1[arr_idx["Secondary Email"]], remove_subject, html)

        if user_prim2 is not None and row_prim2 != row_find:
            if user_prim2[arr_idx["Secondary Expired"]] == "FALSE":
                can_update = False
            elif user_prim2[arr_idx["Secondary Expired"]] == "TRUE":
                cells.append(Cell(row_prim2, wks_idx["Secondary Email"], ""))
                if user_prim2[arr_idx["Primary Email"]] != "" and user_prim2[arr_idx["Primary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_prim2[arr_idx["First Name"]],
                                           last=user_prim2[arr_idx["Last Name"]],
                                           email=user_prim2[arr_idx["Secondary Email"]])
                    send_email(user_prim2[arr_idx["Primary Email"]], remove_subject, html)

        if user_sec1 is not None and row_sec1 != row_find:
            if user_sec1[arr_idx["Primary Expired"]] == "FALSE":
                can_update = False
            elif user_sec1[arr_idx["Primary Expired"]] == "TRUE":
                cells.append(Cell(row_sec1, wks_idx["Primary Email"], ""))
                if user_sec1[arr_idx["Secondary Email"]] != "" and user_sec1[arr_idx["Secondary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_sec1[arr_idx["First Name"]],
                                           last=user_sec1[arr_idx["Last Name"]],
                                           email=user_sec1[arr_idx["Primary Email"]])
                    send_email(user_sec1[arr_idx["Secondary Email"]], remove_subject, html)

        if user_sec2 is not None and row_sec2 != row_find:
            if user_sec2[arr_idx["Secondary Expired"]] == "FALSE":
                can_update = False
            elif user_sec2[arr_idx["Secondary Expired"]] == "TRUE":
                cells.append(Cell(row_sec2, wks_idx["Secondary Email"], ""))
                if user_sec2[arr_idx["Primary Email"]] != "" and user_sec2[arr_idx["Primary Verified"]] == "TRUE":
                    html = render_template("deleting_email.html",
                                           first=user_sec2[arr_idx["First Name"]],
                                           last=user_sec2[arr_idx["Last Name"]],
                                           email=user_sec2[arr_idx["Secondary Email"]])
                    send_email(user_sec2[arr_idx["Primary Email"]], remove_subject, html)

        if len(cells) > 0:
            wks.update_cells(cells)

        if not can_update:
            return render_template("error4.html")

        else:
            cells.clear()

            if (user[arr_idx["Primary Email"]] == sec_email and user[arr_idx["Secondary Email"]] == prim_email):
                swap = True
                cells.append(Cell(
                    row_find,
                    wks_idx["Primary Verified"],
                    user[arr_idx["Secondary Verified"]],
                ))
                cells.append(Cell(
                    row_find,
                    wks_idx["Secondary Verified"],
                    user[arr_idx["Primary Verified"]],
                ))

                cells.append(Cell(
                    row_find,
                    wks_idx["Primary Bounced"],
                    user[arr_idx["Secondary Bounced"]],
                ))
                cells.append(Cell(
                    row_find,
                    wks_idx["Secondary Bounced"],
                    user[arr_idx["Primary Bounced"]],
                ))

                cells.append(Cell(
                    row_find,
                    wks_idx["Primary Expired"],
                    user[arr_idx["Secondary Expired"]],
                ))
                cells.append(Cell(
                    row_find,
                    wks_idx["Secondary Expired"],
                    user[arr_idx["Primary Expired"]],
                ))

            # primary OR secondary email are swapped...
            elif user[arr_idx["Primary Email"]] == sec_email:
                swap = True
                cells.append(Cell(
                    row_find,
                    wks_idx["Secondary Verified"],
                    user[arr_idx["Primary Verified"]],
                ))
                cells.append(Cell(
                    row_find,
                    wks_idx["Secondary Bounced"],
                    user[arr_idx["Primary Bounced"]],
                ))
                cells.append(Cell(
                    row_find,
                    wks_idx["Secondary Expired"],
                    user[arr_idx["Primary Expired"]],
                ))
                cells.append(Cell(row_find, wks_idx["Primary Verified"], "FALSE"))
                cells.append(Cell(row_find, wks_idx["Primary Bounced"], ""))
                cells.append(Cell(row_find, wks_idx["Primary Expired"], "FALSE"))

                need_verif = True

                p_token = generate_token(prim_email)
                confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                html = render_template(
                    "verify_email.html",
                    first=user[arr_idx["First Name"]],
                    last=user[arr_idx["Last Name"]],
                    confirm_url=confirm_url,
                )
                send_email(prim_email, verif_subject, html)
                sent_to_prim = True

                thread = Thread(target=expiry_timer, args=(prim_email, "Primary Email", "Primary Verified"))
                thread.start()

            elif user[arr_idx["Secondary Email"]] == prim_email:
                swap = True
                cells.append(Cell(
                    row_find,
                    wks_idx["Primary Verified"],
                    user[arr_idx["Secondary Verified"]],
                ))
                cells.append(Cell(row_find, wks_idx["Secondary Verified"], "FALSE"))
                cells.append(Cell(row_find, wks_idx["Secondary Bounced"], ""))
                cells.append(Cell(row_find, wks_idx["Secondary Expired"], "FALSE"))

                need_verif = True

                s_token = generate_token(sec_email)
                confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                html = render_template(
                    "verify_email.html",
                    first=user[arr_idx["First Name"]],
                    last=user[arr_idx["Last Name"]],
                    confirm_url=confirm_url,
                )
                send_email(sec_email, verif_subject, html)
                sent_to_sec = True

                thread = Thread(target=expiry_timer, args=(sec_email, "Secondary Email", "Secondary Verified"))
                thread.start()

            # changing primary to different email
            if user[arr_idx["Primary Email"]] != prim_email and not swap:
                need_verif = True

                if not sent_to_prim:
                    p_token = generate_token(prim_email)
                    confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user[arr_idx["First Name"]],
                        last=user[arr_idx["Last Name"]],
                        confirm_url=confirm_url,
                    )
                    cells.append(Cell(row_find, wks_idx["Primary Verified"], "FALSE"))
                    cells.append(Cell(row_find, wks_idx["Primary Bounced"], ""))
                    cells.append(Cell(row_find, wks_idx["Primary Expired"], "FALSE"))

                    send_email(prim_email, verif_subject, html)
                    sent_to_prim = True

                    thread = Thread(target=expiry_timer, args=(prim_email, "Primary Email", "Primary Verified"))
                    thread.start()

            # changing secondary to different email
            if user[arr_idx["Secondary Email"]] != sec_email and not swap:
                need_verif = True

                if not sent_to_sec:
                    s_token = generate_token(sec_email)
                    confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user[arr_idx["First Name"]],
                        last=user[arr_idx["Last Name"]],
                        confirm_url=confirm_url,
                    )
                    cells.append(Cell(row_find, wks_idx["Secondary Verified"], "FALSE"))
                    cells.append(Cell(row_find, wks_idx["Secondary Bounced"], ""))
                    cells.append(Cell(row_find, wks_idx["Secondary Expired"], "FALSE"))

                    send_email(sec_email, verif_subject, html)
                    sent_to_sec = True

                    thread = Thread(target=expiry_timer, args=(sec_email, "Secondary Email", "Secondary Verified"))
                    thread.start()

            cells.append(Cell(row_find, wks_idx["First Name"], form.first_name.data))
            cells.append(Cell(row_find, wks_idx["Last Name"], form.last_name.data))
            cells.append(Cell(row_find, wks_idx["Primary Email"], prim_email))
            cells.append(Cell(row_find, wks_idx["Secondary Email"], sec_email))

            for row in edit_form.query.all():
                if row.field_type == "Checkbox":
                    vals = []
                    choices = checkbox_get_choices(row.options)
                    for key in request.form.getlist(row.label):
                        vals.append(choices[int(key)][1])
                    cells.append(Cell(row_find, wks_idx[row.label], "\n".join(vals)))
                else:
                    cells.append(Cell(row_find, wks_idx[row.label], request.form[row.label]))

            if len(cells) > 0:
                wks.update_cells(cells)

            cells.clear()

            user = wks.row_values(row_find)

            if user[arr_idx["Primary Verified"]] == "FALSE":
                cells.append(Cell(row_find, wks_idx["Primary Subscribed"], "FALSE"))
                if not sent_to_prim:
                    need_verif = True
                    p_token = generate_token(prim_email)
                    confirm_url = url_for("registration.confirm", token=p_token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user[arr_idx["First Name"]],
                        last=user[arr_idx["Last Name"]],
                        confirm_url=confirm_url,
                    )
                    send_email(prim_email, verif_subject, html)

            if user[arr_idx["Secondary Verified"]] == "FALSE":
                cells.append(Cell(row_find, wks_idx["Secondary Subscribed"], "FALSE"))
                if not sent_to_sec:
                    need_verif = True
                    s_token = generate_token(sec_email)
                    confirm_url = url_for("registration.confirm", token=s_token, _external=True)
                    html = render_template(
                        "verify_email.html",
                        first=user[arr_idx["First Name"]],
                        last=user[arr_idx["Last Name"]],
                        confirm_url=confirm_url,
                    )
                    send_email(sec_email, verif_subject, html)

            if user[arr_idx["Primary Verified"]] == "TRUE":
                cells.append(Cell(
                    row_find,
                    wks_idx["Primary Subscribed"],
                    form.primary_subscribe.data,
                ))

            if user[arr_idx["Secondary Verified"]] == "TRUE":
                cells.append(Cell(
                    row_find,
                    wks_idx["Secondary Subscribed"],
                    form.secondary_subscribe.data,
                ))

            cells.append(Cell(
                row_find,
                wks_idx["Last Updated"],
                str(datetime.now().replace(second=0, microsecond=0)),
            ))

            cells.append(Cell(row_find, wks_idx["Info Completed"], "TRUE"))

            if len(cells) > 0:
                wks.update_cells(cells)

            if need_verif:
                return render_template("need_verif.html")
            else:
                return render_template("thanks_update.html")

    else:
        return render_template("update_form.html", form=form, token=token)
