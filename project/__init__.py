import os
from os import path
from datetime import datetime
from flask import Flask, render_template, request, send_file, jsonify, redirect, url_for, session
from flask_caching import Cache
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, login_user, logout_user, login_required
from flask_admin import Admin
from flask_migrate import Migrate
from config.default import Config, APP_ROOT
from werkzeug.security import generate_password_hash
import firebase_admin
from firebase_admin import credentials, auth
from flask import flash
import pytz
# Flask
app = Flask(__name__)

app.config.from_object(Config())

cache = Cache(app)
email_from_form = "usr"
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri="memory://",
    default_limits=["15 per 30 seconds"],
    default_limits_exempt_when=lambda: request.path.startswith("/admin")
)

@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(429)
def too_many_requests(e):
    return render_template("429.html"), 429


# SQLAlchemy
db = SQLAlchemy()
db.init_app(app)

migrate = Migrate(app, db)
import boto3

ses = boto3.client('ses',
                   region_name='us-west-2',
                   aws_access_key_id=app.config["AWS_ACCESS_KEY_ID"],
                   aws_secret_access_key=app.config["AWS_SECRET_ACCESS_KEY"])

sqs = boto3.client('sqs',
                   region_name='us-west-2',
                   aws_access_key_id=app.config["AWS_ACCESS_KEY_ID"],
                   aws_secret_access_key=app.config["AWS_SECRET_ACCESS_KEY"])


import pytz
tz = pytz.timezone("America/Los_Angeles")


# Models
from project.models import user, edit_form, event

@app.context_processor
def inject_event():
    return dict(event=event.query.filter_by(live=True).order_by(event.id.desc()).first())


# Google Sheet
import gspread
from gspread.client import BackoffClient

gc = gspread.service_account(client_factory=BackoffClient)
sh = gc.open(app.config["CURRENT_SPREADSHEET"])

worksheets = []
for worksheet in sh.worksheets():
    worksheets.append(worksheet.title)

if "Members" not in worksheets:
    sh.add_worksheet("Members", 1, 100)
    row = [
        "Order", "First Name", "Last Name", "When Started", "Last Updated", "Primary Email", "Primary Verified",
        "Primary Subscribed", "Primary Expired", "Primary Bounced", "Secondary Email", "Secondary Verified",
        "Secondary Subscribed", "Secondary Expired", "Secondary Bounced", "Info Completed"
    ]
    sh.worksheet("Members").append_row(row)

    with app.app_context():
        for row in edit_form.query.all():
            if row.label not in sh.worksheet("Members").row_values(1):
                sh.worksheet("Members").update_cell(1, len(sh.worksheet("Members").row_values(1)) + 1, row.label)

if "Logs" not in worksheets:
    sh.add_worksheet("Logs", 1, 100)
    row = [
        "Order", "Transaction", "DateTime"
    ]
    sh.worksheet("Logs").append_row(row)

wks = sh.worksheet("Members")
logs = sh.worksheet("Logs")


def get_wks_records(wks):
    wks_records = wks.get_all_records()
    for i, row in enumerate(wks_records, start=2):
        row['Row'] = i
    return wks_records

def get_wks_columns(wks):
    header_row = wks.row_values(1)
    wks_columns = {header_row[i]: i+1 for i in range(len(header_row))}
    return wks_columns


# Flask Blueprints
from project.views.home import home_blueprint
from project.views.registration import registration_blueprint
from project.views.update import update_blueprint
from project.views.events import events_blueprint
from project.views.geo import geo_blueprint

app.register_blueprint(home_blueprint)
app.register_blueprint(registration_blueprint)
app.register_blueprint(update_blueprint)
app.register_blueprint(events_blueprint)
app.register_blueprint(geo_blueprint)


# Flask Admin
from project.views.admin import IndexView, UserModelView, EditFormModelView, EventModelView, ContactView, CatchBouncesView

admin_app = Admin(app, name="Admin Page", index_view=IndexView(), template_mode="bootstrap3")
admin_app.add_view(UserModelView(user, db.session, name="Administrators"))
admin_app.add_view(EditFormModelView(edit_form, db.session, name="Edit Form"))
admin_app.add_view(EventModelView(event, db.session, name="Events"))
admin_app.add_view(ContactView(name="Contact", endpoint="contact"))
admin_app.add_view(CatchBouncesView(name="Catch Bounces", endpoint="catch_bounces"))





#team 325 stuff

#importing the models 

from project.models import db, RefRegistration, RefJudge, RefParking, RefProject, RefRoom, TblCheckIn, TblEvent, TblEventJudge, TblQr, TblCheckIn
from project.forms.admin2_form import add_Registration, add_Judge,add_Parking,add_Project,add_Room,add_Event,add_EventJudge, RemoveUserForm






# Flask Admin2

@app.route('/admin2')
def admin2():
    """
    This function is the route handler for the '/admin2' endpoint.
    It checks if the user is authenticated, and if not, redirects them to the login page.
    It then retrieves all the registrations from the database and renders the 'admin_dash.html' template,
    passing the registrations as a parameter.

    Returns:
        The rendered template 'admin_dash.html' with the registrations as a parameter.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))
    registers = RefRegistration.query.order_by(RefRegistration.User_ID).all()
    return render_template('admin2/admin_dash.html', registers=registers)


@app.route('/ref_registration', methods=['GET', 'POST'])
def ref_registration():
    """
    View function for the '/ref_registration' route.
    Allows registered users to add new registrations to the database and update a Google Sheets worksheet.

    Returns:
        If the user is not authenticated, redirects to the login page.
        If the form is submitted successfully, redirects to the 'ref_registration' page.
        Otherwise, renders the 'admin2/ref_registration.html' template with the form and existing registrations.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))

    registers = RefRegistration.query.order_by(RefRegistration.User_ID).all()
    form = RemoveUserForm()
    form.User_ID.choices = [(attende.User_ID, f"{attende.First_Name} {attende.Last_Name} (ID: {attende.User_ID})") for attende in registers]

    if form.validate_on_submit():
        user_to_remove = RefRegistration.query.get(form.User_ID.data)
        db.session.delete(user_to_remove)
        db.session.commit()
    return render_template('admin2/ref_registration.html', form=form, registers=registers)


@app.route('/ref_Judge', methods=['GET', 'POST'])
def ref_Judge():
    """
    View function for the '/ref_Judge' route.
    This function handles the registration of judges and rendering the 'admin2/ref_Judge.html' template.

    Returns:
        If the user is not authenticated, it redirects to the login page.
        If the form is submitted and validated successfully, it registers the judge and redirects to the '/ref_Judge' route.
        Otherwise, it renders the 'admin2/ref_Judge.html' template with the form and the list of registered judges.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))
    registers = RefRegistration.query.order_by(RefRegistration.User_ID).all()

    form = add_Judge()
    form.User_ID.choices = [(attende.User_ID, f"{attende.First_Name} {attende.Last_Name} (ID: {attende.User_ID})") for attende in registers]
        
    if form.validate_on_submit():
        selected_user_id = form.User_ID.data
        selected_user = RefRegistration.query.get(selected_user_id)
        new_judge = RefJudge(ID=selected_user_id, First_name=selected_user.First_Name, Last_Name=selected_user.Last_Name)
        db.session.add(new_judge)
        db.session.commit()
        flash('Judge registered successfully.', 'success')
        return redirect(url_for('ref_Judge'))
    judges = RefJudge.query.order_by(RefJudge.ID).all()
    return render_template('admin2/ref_Judge.html', form=form, Judges=judges)

@app.route('/ref_Parking', methods=['GET', 'POST'])
def ref_Parking():
    """
    This function handles the '/ref_Parking' route of the application.
    It is responsible for displaying and processing the form for adding parking information.
    If the user is not authenticated, it redirects to the login page.
    If the form is submitted and valid, it adds the parking information to the database.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))
    parking = RefParking.query.order_by(RefParking.ID).all()
    form = add_Parking()
    
    if form.validate_on_submit():
        new_Parking = RefParking(Name = form.Name.data,X_Location = form.X_Location.data,Y_Location = form.Y_Location.data)
        db.session.add(new_Parking)
        db.session.commit()
        flash('Parking input successfully.', 'success')
        return redirect(url_for('ref_Parking'))
    return render_template('admin2/ref_parking.html', form=form, parking=parking)

@app.route('/ref_Project', methods=['GET', 'POST'])
def ref_Project():
    """
    View function for the '/ref_Project' route.
    This function handles GET and POST requests for the '/ref_Project' route.
    If the user is not authenticated, it flashes a warning message and redirects to the login page.
    It retrieves all projects from the database and renders the 'admin2/ref_project.html' template,
    along with the 'add_Project' form and the list of projects.
    If the form is submitted and validated, it creates a new project in the database,
    flashes a success message, and redirects to the '/ref_Project' route.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))
    projects = RefProject.query.order_by(RefProject.ID).all()
    form = add_Project()
    if form.validate_on_submit():
        new_Project = RefProject(Project_Name=form.Project_Name.data, Project_Des=form.Project_Des.data, 
                                 Mentor=form.Mentor.data, Mentor1=form.Mentor1.data, Mentor2=form.Mentor2.data)
        db.session.add(new_Project)
        db.session.commit()
        flash('Project registered successfully.', 'success')
        return redirect(url_for('ref_Project'))
    return render_template('admin2/ref_project.html', form=form, projects=projects)


@app.route('/ref_Room', methods=['GET', 'POST'])
def ref_Room():
    """
    View function for the '/ref_Room' route.
    Renders the 'admin2/ref_room.html' template and handles the form submission for adding a new room.

    Returns:
        If the user is not authenticated, redirects to the login page.
        If the form is submitted and valid, adds a new room to the database and redirects to the 'ref_Room' page.
        Otherwise, renders the 'admin2/ref_room.html' template with the form and existing rooms.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for(f'admin.login'))
    
    projects = RefProject.query.order_by(RefProject.ID).all()

    form = add_Room()
    form.Project__ID.choices = [(projec_t.ID, f"{projec_t.ID} (ID: {projec_t.Project_Name})") for projec_t in projects]

    if form.validate_on_submit():
        selected_project_id = form.Project__ID.data
        selected_project = RefProject.query.get(selected_project_id)
        new_judge = RefRoom(Name = form.Name.data, Project = selected_project.ID, Link = form.Link.data)
        db.session.add(new_judge)
        db.session.commit()
        flash('Room registered successfully.', 'success')
        return redirect(url_for('ref_Room'))
    
    Rooms = RefRoom.query.order_by(RefRoom.ID).all()
    return render_template('admin2/ref_room.html', form=form,Rooms=Rooms)

@app.route('/tbl_CheckIn', methods=['GET', 'POST'])
def tbl_CheckIn():
    """
    This function handles the '/tbl_CheckIn' route and displays the admin dashboard.

    If the user is not authenticated, it flashes a warning message and redirects to the login page.
    Otherwise, it retrieves all the registrations from the database and renders the admin dashboard template.

    Returns:
        The rendered template 'admin2/admin_dash.html' with the registrations passed as a parameter.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))
        
    Checkins = TblCheckIn.query.order_by(TblCheckIn.ID).all()
    return render_template('admin2/tbl_checkin.html', Checkins=Checkins)

@app.route('/tbl_Event', methods=['GET', 'POST'])
def tbl_Event():
    """
    This function handles the '/tbl_Event' route of the application.
    It is responsible for rendering the 'tbl_event.html' template and processing form submissions.
    If the user is not authenticated, it redirects to the login page.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))

    projects = RefProject.query.order_by(RefProject.ID).all()
    Rooms = RefRoom.query.order_by(RefRoom.ID).all()

    form = add_Event()
    form.Project_ID.choices = [(project.ID, f"{project.Project_Name}(ID: {project.ID})") for project in projects]
    form.Room_ID.choices = [(Room.ID, f"{Room.Name}  (ID: {Room.ID})") for Room in Rooms]
  
    if form.validate_on_submit():
        selected_project_id = form.Project_ID.data
        selected_project = RefProject.query.get(selected_project_id)
        selected_room_id = form.Room_ID.data
        selected_room = RefRoom.query.get(selected_room_id)
        event_name = 'Event: ' + selected_project.Project_Name + '_' + selected_room.Name
        new_event = TblEvent(Name = event_name, Project_ID = selected_project.ID, Room_ID = selected_room.ID)
        db.session.add(new_event)
        db.session.commit()
        flash('Event registered successfully.', 'success')
        return redirect(url_for('tbl_Event'))
    
    Events = TblEvent.query.order_by(TblEvent.ID).all()
    return render_template('admin2/tbl_event.html', form=form, Events=Events)

@app.route('/tbl_EventJudge', methods=['GET', 'POST'])
def tbl_EventJudge():
    """
    View function for the '/tbl_EventJudge' route.
    Renders the template 'admin2/tbl_event_judge.html' and handles the form submission for adding event judges.

    Returns:
        If the user is not authenticated, redirects to the login page.
        If the form is submitted successfully, redirects to the '/tbl_EventJudge' route.
        Otherwise, renders the 'admin2/tbl_event_judge.html' template with the form and event judges.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))

    judges = RefJudge.query.order_by(RefJudge.ID).all()
    Events = TblEvent.query.order_by(TblEvent.ID).all()

    form = add_EventJudge()
    form.Judge_ID.choices = [(judge.ID, f"{judge.First_name}(ID: {judge.ID})") for judge in judges]
    form.Event_ID.choices = [(event.ID, f"{event.ID}  (ID: {event.ID})") for event in Events]
  
    if form.validate_on_submit():
        selected_Judge_ID = form.Judge_ID.data
        selected_Judge = RefProject.query.get(selected_Judge_ID)

        selected_Event_ID = form.Event_ID.data
        selected_event = RefRoom.query.get(selected_Event_ID)
        
        new_EventJudge = TblEventJudge(Judge_ID = selected_Judge.ID, Event_ID = selected_event.ID,
                                Link = form.Link.data,Link2 = form.Link2.data,Link3 = form.Link3.data,Link4 = form.Link4.data)
        db.session.add(new_EventJudge)
        db.session.commit()
        flash('Event Judge registered successfully.', 'success')
        return redirect(url_for('tbl_EventJudge'))
    
    Event_Judges = TblEvent.query.order_by(TblEvent.ID).all()
    return render_template('admin2/tbl_event_judge.html', form=form, Event_Judges=Event_Judges)



@app.route('/signup', methods=['GET', 'POST'])
def signup():
    return render_template('admin2/signup.html')


@app.route('/Staff', methods=['GET', 'POST'])
def Staff():
    """
    This function handles the '/tbl_Qr' route and renders the 'admin_dash.html' template.

    If the user is not authenticated, it flashes a warning message and redirects to the login page.
    Otherwise, it retrieves all the registrations from the database and passes them to the template.

    Returns:
        The rendered 'admin_dash.html' template with the registrations passed as a parameter.
    """
    if not current_user.is_authenticated:
        flash('Please log in first.', 'warning')
        return redirect(url_for('admin.login'))
    registers = RefRegistration.query.order_by(RefRegistration.User_ID).all()
    return render_template('admin2/admin_dash.html', registers=registers)






# Email Pixel Tracking
@app.route("/tracking_pixel/<email>.png")
def tracking_pixel(email):
    order = int(logs.col_values(1)[-1]) + 1 if logs.col_values(1)[-1].isdigit() else 1
    row = [order, "/tracking_pixel/<email>", str(datetime.now(tz).replace(second=0, microsecond=0).strftime("%Y-%m-%d %I:%M %p")), email]
    logs.append_row(row)

    return send_file("static/images/tracking_pixel.png", mimetype="image/png")











@app.route('/generate')
def home():
    return render_template('staff/index.html')

@app.route('/scan')
def scan():
    #users = auth.list_users().users

    if 'login_id' in session:
        return render_template('scan.html')
    else:
        return redirect(url_for('staff_login'))
        #if session['login_id'] in users:
        #    return render_template('scan.html')
        #return redirect(url_for('staff_login'))
    #else:
    #    return redirect(url_for('staff_login'))

@app.route('/manual')
def manual():
    return render_template('manual.html')


@app.route('/manual_add', methods=['GET', 'POST'])
def manual_add():
    """
    Handle the manual addition of a user.

    This function is responsible for handling the form submission when a user is manually added.
    It extracts the form data, registers the user in the database, and checks the user in.
    If the user is already checked in, it displays an error message.
    After successful registration and check-in, it appends the user's information to a Google Sheet.

    Returns:
        If the request method is 'POST':
            - If the user is already checked in, it renders the 'manual.html' template with an error message.
            - If the registration and check-in are successful, it renders the 'manual.html' template with a success message.
        If the request method is 'GET':
            - It renders the 'manual.html' template.
    """
    if request.method == 'POST':
        # Extract form data
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        organization = request.form.get('organization', '')
        role = request.form.get('role', '')

        now_utc = datetime.now(pytz.utc)
        now_pacific = now_utc.astimezone(pytz.timezone('America/Los_Angeles'))

        wks_columns = get_wks_columns(wks)
        user_id = int(wks.col_values(wks_columns["Order"])[-1]) + 1

        cell = wks.find(email)
        if cell: 
            error_message2 = "Attendee already checked in"
            return render_template('manual.html', error_message2=error_message2)
        else: 
            # Register the user
            new_user = RefRegistration(
                First_Name=first_name,
                Last_Name=last_name,
                Email=email,
                Secondary_Email='',
                Organization=organization,
                Role=role,
                Primary_verified=0,
                Last_Updated=now_pacific.strftime("%d/%m/%Y %H:%M:%S")
            )
            db.session.add(new_user)
            db.session.commit()

            # Check the user in
            new_checkin = TblCheckIn(
                User_ID=new_user.Email,
                Checkin_Time=now_pacific.strftime("%d/%m/%Y %H:%M:%S")
            )
            db.session.add(new_checkin)
            db.session.commit()
            
            sheet = sh.worksheet("Members")
            row = [
                user_id,
                new_user.First_Name,
                new_user.Last_Name,
                new_user.Last_Updated,
                new_user.Last_Updated,
                new_user.Email,
                0,
                0,
                0,
                '',
                new_user.Secondary_Email,
                0,
                0,
                0,
                '',
                'FALSE',
                '',
                new_user.Organization,
                new_user.Role, 
                '', 
                # 1, 
                # now_pacific.strftime("%d/%m/%Y %H:%M:%S")
            ]
            wks.append_row(row)

            #sheet name from google sheet I2G Membership
            sheet2 = sh.worksheet("I2G Summer testing (locally)")
            row2 = [
                user_id,
                new_user.First_Name,
                new_user.Last_Name,
                new_user.Last_Updated,
                new_user.Last_Updated,
                new_user.Email,
                new_user.Secondary_Email,
                new_user.Role,
                new_user.Organization,
                'n/a',
                'n/a',
                'n/a',
                'n/a',
                1, 
                now_pacific.strftime("%d/%m/%Y %H:%M:%S")
            ]
            sheet2.append_row(row2)

            success_message = "Check-In Successful!"

            return render_template('manual.html', success_message=success_message)
    return render_template('manual.html')


@app.route('/checkin', methods=['GET', 'POST'])
def checkin():
    """
    Handle the check-in functionality for attendees.

    This function is responsible for handling the check-in process for attendees. It receives a POST request
    containing the new user ID and performs the following steps:
    1. Find the cell in the worksheet corresponding to the provided user ID.
    2. If the cell is found, retrieve the necessary information such as QR code, check-in status, email ID, etc.
    3. If the attendee has already checked in, display an error message.
    4. Otherwise, update the check-in status, check-in time, and QR code in the worksheet.
    5. Update the check-in status and check-in time in a separate worksheet.
    6. Store the check-in information in the database.
    7. Display a success message if the check-in is successful.
    8. If the attendee does not exist, display an error message.

    Returns:
        A rendered template with success or error messages based on the check-in result.
    """
    # if request.method == 'POST':
    #     qr_id = request.form['new_user_id']
    #     cell = wks.find(qr_id)

    #     if cell:
    #         val = cell.row
    #         value = str(val)
    #         qr_cell = 'T' + value
    #         qr_code = wks.acell(qr_cell).value
    #         checkin_cell = 'U' + value
    #         checkin_time_cell = 'V' + value
    #         email_cell = 'F' + value
    #         email_id = wks.acell(email_cell).value

    #         check = wks.acell(checkin_cell).value
    #         if check == '1':
    #             error_message2 = "Attendee already checked in"
    #             return render_template('scan.html', error_message2=error_message2)
    #         else:
    #             wks.update(checkin_cell, '1')
    #             now_utc = datetime.now(pytz.utc)
    #             now_pacific = now_utc.astimezone(pytz.timezone('America/Los_Angeles'))
    #             wks.update(checkin_time_cell, now_pacific.strftime("%d/%m/%Y %H:%M:%S"))

    #             wks2 = sh.worksheet("I2G Spring 2024")
    #             cell = wks2.find(email_id)

    #             val = cell.row
    #             value = str(val)
    #             qr_cell = 'M' + value
    #             checkin_cell = 'N' + value
    #             checkin_time_cell = 'O' + value

    #             wks2.update(qr_cell, qr_code)
    #             wks2.update(checkin_cell, '1')
    #             now_utc = datetime.now(pytz.utc)
    #             now_pacific = now_utc.astimezone(pytz.timezone('America/Los_Angeles'))
    #             wks2.update(checkin_time_cell, now_pacific.strftime("%d/%m/%Y %H:%M:%S"))

    #             new_checkin = TblCheckIn(User_ID=qr_id, Checkin_Time=now_pacific.strftime("%d/%m/%Y %H:%M:%S"))
    #             db.session.add(new_checkin)
    #             db.session.commit()

    #             success_message = "Check-In Successful!"

    #             return render_template('scan.html', success_message=success_message)
    #     else:
    #         error_message = "Invalid: Attendee does not exist"
    #         return render_template('scan.html', error_message=error_message)

    # return render_template('scan.html')


    if request.method == 'POST':
        #sheet name from google sheet I2G Membership
        wks = sh.worksheet("I2G Summer testing (locally)")

        qr_id = request.form['new_user_id']
        cell = wks.find(qr_id)

        if cell:
            val = cell.row
            value = str(val)
            qr_cell = 'M' + value
            checkin_cell = 'N' + value
            checkin_time_cell = 'O' + value

            check = wks.acell(checkin_cell).value
            if check == '1':
                error_message2 = "Attendee already checked in"
                return render_template('scan.html', error_message2=error_message2)
            else:
                # wks.update(qr_cell, qr_code)
                wks.update(checkin_cell, '1')
                now_utc = datetime.now(pytz.utc)
                now_pacific = now_utc.astimezone(pytz.timezone('America/Los_Angeles'))
                wks.update(checkin_time_cell, now_pacific.strftime("%d/%m/%Y %H:%M:%S"))

                # wks2 = sh.worksheet("Members")
                # cell = wks2.find(email_id)

                # val = cell.row
                # value = str(val)
                # # qr_cell = 'T' + value
                # # qr_code = wks.acell(qr_cell).value
                # checkin_cell = 'U' + value
                # checkin_time_cell = 'V' + value
                # # email_cell = 'F' + value
                # # email_id = wks.acell(email_cell).value
    
                # wks.update(checkin_cell, '1')
                # now_utc = datetime.now(pytz.utc)
                # now_pacific = now_utc.astimezone(pytz.timezone('America/Los_Angeles'))
                # wks.update(checkin_time_cell, now_pacific.strftime("%d/%m/%Y %H:%M:%S"))

                new_checkin = TblCheckIn(User_ID=qr_id, Checkin_Time=now_pacific.strftime("%d/%m/%Y %H:%M:%S"))
                db.session.add(new_checkin)
                db.session.commit()

                success_message = "Check-In Successful!"

                return render_template('scan.html', success_message=success_message)
        else:
            error_message = "Invalid: Attendee does not exist"
            return render_template('scan.html', error_message=error_message)
    return render_template('scan.html')
    #     # return redirect(url_for('/i2g/')) 




#firebase stuff team CSE-325 

cred = credentials.Certificate('firebase_serviceAccountKey.json')
firebase_admin.initialize_app(cred)



@app.route('/add_firebase_user', methods=['POST'])
def add_firebase_user():
    """
    Add a new user to Firebase Authentication.

    This function receives a POST request with JSON data containing the email and password of the user to be created.
    It creates a new user in Firebase Authentication using the provided email and password.
    If the user is created successfully, it returns a JSON response with a success message and the user's unique ID.
    If there is an error during the user creation process, it returns a JSON response with a failure message and the error details.

    Returns:
        A JSON response with a success or failure message and additional information.

    Raises:
        Exception: If there is an error during the user creation process.
    """
    data = request.json
    email = data.get('email')
    password = data.get('password')
    try:
        user = auth.create_user(email=email, password=password)
        return jsonify({"success": True, "message": f"User {user.uid} created successfully."}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/remove_firebase_user', methods=['POST'])
@login_required
def remove_firebase_user():
    email = request.form.get('email')
    """
    Removes a Firebase user with the given user_uid.

    Args:
        user_uid (str): The unique identifier of the user to be removed.

    Returns:
        redirect: Redirects back to the admin page.

    Raises:
        firebase_admin.exceptions.FirebaseError: If there is an error while removing the user.
        Exception: If there is an unexpected error.

    """
    if email:
        try:
            # Get the user details by email
            user = auth.get_user_by_email(email)

            # Remove the Firebase user
            auth.delete_user(user.uid)
            flash('User successfully removed', 'success')
        except firebase_admin.auth.UserNotFoundError:
            # Handle case where user is not found
            flash('User not found', 'error')
        except firebase_admin.exceptions.FirebaseError as e:
            # Handle Firebase errors
            flash(f'Error removing user: {e}', 'error')
        except Exception as e:
            # Handle other possible errors
            flash(f'Unexpected error: {e}', 'error')
    else:
        flash('Please provide an email', 'error')
    # Redirect back to the admin page or handle accordingly
    return redirect(url_for('Staff'))



#staff login 
@app.route("/staff_login", methods=['GET'])
def staff_login():
    #users = auth.list_users().users
    if 'login_id' in session:
        return redirect(url_for('scan'))
    else:
        return render_template("Staff/login.html")
        #if session['login_id'] in users:
            #return redirect(url_for('scan'))
        #return render_template("Staff/login.html")
    #else:
    #    return render_template("Staff/login.html")

#uM1GxRv586F0MXg3DtVU78BQZnMvLWr6gD4p3Fe36M8x7Sf1gEyFL1HLeXPwVvCyWcKzQecJ45CfQXVNiNG2tFj8wvJuPT5SfUtu7YA7BVWVbWWY73bnWn4j85tX7ZJkbdf7Tfa5mB9JqgmewjHgwGSyUtqwhSdLSeKRn3GH61Vnhpq0tNMSwknFwCyWq97BxEExej2SkFMEDTSLki

@app.route('/uM1GxRv586F0MXg3DtVU78BQZnMvLWr6gD4p3Fe36M8x7Sf1gEyFL1HLeXPwVvCyWcKzQecJ45CfQXVNiNG2tFj8wvJuPT5SfUtu7YA7BVWVbWWY73bnWn4j85tX7ZJkbdf7Tfa5mB9JqgmewjHgwGSyUtqwhSdLSeKRn3GH61Vnhpq0tNMSwknFwCyWq97BxEExej2SkFMEDTSLki', methods=['GET'])
def uM1GxRv586F0MXg3DtVU78BQZnMvLWr6gD4p3Fe36M8x7Sf1gEyFL1HLeXPwVvCyWcKzQecJ45CfQXVNiNG2tFj8wvJuPT5SfUtu7YA7BVWVbWWY73bnWn4j85tX7ZJkbdf7Tfa5mB9JqgmewjHgwGSyUtqwhSdLSeKRn3GH61Vnhpq0tNMSwknFwCyWq97BxEExej2SkFMEDTSLki():
    #user_id = request.args.get('userId')
    #print(user_id)
    #if user_id:
    #user_id = request.args.get('userId')
    session['login_id'] = 'IN'
    return redirect(url_for('scan'))
    #else:
    #    return redirect(url_for('staff_login'))


#donteeeeeeee
@app.route("/staff_logout")
def staff_logout():
    #remove the user id from the session
    session.pop('login_id',None)
    #session['login_id'] = None
    return redirect(url_for('staff_login'))

@app.route("/staff")
def staff():
    return render_template("staff.html")




@app.route('/view_staff_logins', methods=['GET'])
def view_staff_logins():
    if 'login_id' in session:
        users = auth.list_users().users
        users_data = [{"uid": user.uid, "email": user.email} for user in users]
        return jsonify(users_data), 200
    else:
        return redirect(url_for('staff_login'))
    #users = auth.list_users().users
    #users_data = [{"uid": user.uid, "email": user.email} for user in users]
    #return jsonify(users_data), 200





#firbase end

# Flask Login Manager
login_manager = LoginManager(app)
login_manager.session_protection = "basic"
login_manager.login_view = "admin.login"


@login_manager.user_loader
def load_user(user_id):
    return user.query.get(user_id)


if not path.exists(APP_ROOT + "/db"):
    os.makedirs(APP_ROOT + "/db")
if not path.exists(APP_ROOT + "/db/data.sqlite3"):
    with app.app_context():
        db.create_all()
        u = user("Admin", "Admin", "admin@admin.com", generate_password_hash("admin"), "superadmin")
        db.session.add(u)
        db.session.commit()
