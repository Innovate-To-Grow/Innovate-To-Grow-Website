import urllib
import datetime

from flask import Flask, render_template, request, flash, jsonify
from flask_login import LoginManager, login_user, login_required, logout_user
from flask_admin import Admin
from extensions import db
from models import *  # Ensure models are imported
import firebase_admin
from firebase_admin import credentials, auth

cred = credentials.Certificate('serviceAccountKey.json')
firebase_admin.initialize_app(cred)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///main.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret_key'

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
from flask_admin.contrib.sqla import ModelView
from flask_login import current_user
from flask import redirect, url_for


class AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for('login'))


# Setup Flask-Admin
# Utility function to add an admin user - Use this carefully!
def add_admin_user():
    new_admin = TblAdmin(User_name='admin2')  # Create the user without setting the password
    new_admin.password = 'i2g_mobile'  # Set the password using the property setter, which hashes the password
    db.session.add(new_admin)
    db.session.commit()


# with app.app_context():
# add_admin_user()  # Uncomment to run once and then comment it out again

@login_manager.user_loader
def load_user(user_id):
    return TblAdmin.query.get(int(user_id))


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/scan')
def scan():
    return render_template('scan.html')


# login for flask admin
# Login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = TblAdmin.query.filter_by(User_name=username).first()
        if user and user.verify_password(password):  # Use verify_password method
            login_user(user)
            return redirect(url_for('admin.index'))  # Ensure this points to your Flask-Admin URL
    return render_template(
        'login.html')  # Render a login form template on GET request  return 'Login Page, create your login form here.'


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# update the user info api
@app.route('/update', methods=['GET', 'POST'])
def update():
    if request.method == 'POST':
        # Retrieve the user's email from the form data
        email = request.form['email']

        # Find the user by email
        user = RefRegistration.query.filter_by(Email=email).first()

        if user:
            # Update user's information
            user.First_Name = request.form['first_name']
            user.Last_Name = request.form['last_name']
            user.Secondary_Email = request.form['secondary_email']
            user.Organization = request.form.get('organization', user.Organization)  # Keep existing if not provided
            user.Role = request.form.get('role', user.Role)  # Keep existing if not provided
            user.Last_Updated = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')  # Update the last updated time

            # Commit changes
            db.session.commit()

            # Redirect or inform the user of successful update
            return redirect(url_for('home'))  # Assuming you want to redirect to the home page
        else:
            # Handle case where user is not found
            return 'User not found', 404

    # Display the form for GET request
    return render_template('update.html')


@app.route('/checkin', methods=['GET', 'POST'])
def checkin():
    if request.method == 'POST':
        new_user_id = request.form['new_user_id']
        checkin_user_id = RefRegistration.query.filter_by(User_ID=new_user_id).first()
        # if checkin_user_id or not (TblCheckIn.query.filter_by(TblCheckIn.User_ID == checkin_user_id)):
        if checkin_user_id:
            checked_user_id = TblCheckIn.query.filter_by(User_ID=new_user_id).first()
            if checked_user_id:
                error_message2 = "User ID already checked in"
                return render_template('scan.html', error_message2=error_message2)
            else:
                new_checkin = TblCheckIn(User_ID=new_user_id, Checkin_Time=datetime.datetime.now())
                db.session.add(new_checkin)
                db.session.commit()
                # user_firstname = checkin_user_id.First_Name
                # user_lastname = checkin_user_id.Last_Name
                success_message = "Check-In Successful!"
                # return render_template('scan.html', user_firstname=user_firstname, user_lastname=user_lastname, success_message=success_message)
                return render_template('scan.html', success_message=success_message)
        else:
            error_message = "Invalid: User ID does not exist"
            return render_template('scan.html', error_message=error_message)
    # checkin_user_id = RefRegistration.query.filter_by(User_ID=new_user_id).first()
    # success_message = "Check-In Successful!"
    return render_template('scan.html')
    # return redirect(url_for('/i2g/')) 


# login for flask admin
@app.route('/email')
def email():
    return render_template('email.html')


# register for event
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Extract form data
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        secondary_email = request.form['secondary_email']
        organization = request.form.get('organization', '')  # Optional, provide default
        role = request.form.get('role', '')  # Optional, provide default

        # Create a new user instance
        new_user = RefRegistration(
            First_Name=first_name,
            Last_Name=last_name,
            Email=email,
            Secondary_Email=secondary_email,
            Organization=organization,
            Role=role,
            Last_Updated=datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            # Assuming Last_Updated requires a string format
        )

        # Add to the database session and commit
        db.session.add(new_user)
        db.session.commit()

        # Redirect or inform the user of successful registration
        return redirect(url_for('home'))  # Assuming you want to redirect to the home page
    return render_template('register.html')


@app.route('/manual_checkin', methods=['GET', 'POST'])
def manual_checkin():
    if request.method == 'POST':
        user_identifier = request.form['user_identifier']  # Can be either User_ID or Email
        user = None

        # Try to interpret the identifier as an integer User_ID
        try:
            user_id = int(user_identifier)
            user = RefRegistration.query.get(user_id)
        except ValueError:
            # If not an integer, assume it's an email
            user = RefRegistration.query.filter_by(Email=user_identifier).first()

        if user:
            # Check if the user is already checked in
            existing_checkin = TblCheckIn.query.filter_by(User_ID=user.User_ID).first()
            if not existing_checkin:
                # Not checked in, proceed with check-in
                checkin_time = datetime.datetime.now()
                new_checkin = TblCheckIn(User_ID=user.User_ID, Checkin_Time=checkin_time)
                db.session.add(new_checkin)
                db.session.commit()
                flash('Check-in successful.', 'success')
            else:
                flash('User already checked in.', 'error')
        else:
            flash('User not found.', 'error')

    return render_template('manual_checkin.html')


# staff login

@app.route('/admin')
def admin():
    return render_template('admin.html')


@app.route('/fadmin')
def fadmin():
    return render_template('fadmin.html')


@app.route('/manual_add', methods=['GET', 'POST'])
def manual_add():
    if request.method == 'POST':
        # Extract form data
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        email = request.form['email']
        secondary_email = request.form['secondary_email']
        organization = request.form.get('organization', '')
        role = request.form.get('role', '')

        # Register the user
        new_user = RefRegistration(
            First_Name=first_name,
            Last_Name=last_name,
            Email=email,
            Secondary_Email=secondary_email,
            Organization=organization,
            Role=role,
            Last_Updated=datetime.datetime.now()
        )
        db.session.add(new_user)
        db.session.commit()

        # Check the user in
        new_checkin = TblCheckIn(
            User_ID=new_user.User_ID,
            Checkin_Time=datetime.datetime.now()
        )
        db.session.add(new_checkin)
        db.session.commit()

        # Redirect or inform the user of successful operation
        return f"User registered and checked in. User ID: {new_user.User_ID}"
    return render_template('manual_add.html')


@app.route('/generate_qr', methods=['POST'])
def generate_qr():
    data = request.form['data']
    encoded_data = urllib.parse.quote_plus(data)
    size = "500"  # You can adjust the size as needed
    qr_url = f"https://chart.googleapis.com/chart?chs={size}x{size}&cht=qr&chl={encoded_data}"
    return render_template('show_qr.html', qr_url=qr_url)



@app.route('/add_firebase_user', methods=['POST'])
def add_firebase_user():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    try:
        user = auth.create_user(email=email, password=password)
        return jsonify({"success": True, "message": f"User {user.uid} created successfully."}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route('/remove_firebase_user/<user_uid>', methods=['POST'])
def remove_firebase_user(user_uid):
    try:
        # Remove the Firebase user
        auth.delete_user(user_uid)
        flash('User successfully removed', 'success')
    except firebase_admin.exceptions.FirebaseError as e:
        # Handle Firebase errors
        flash(f'Error removing user: {e}', 'error')
    except Exception as e:
        # Handle other possible errors
        flash(f'Unexpected error: {e}', 'error')

    # Redirect back to the admin page or handle accordingly
    return redirect(url_for('fadmin'))


@app.route('/view_staff_logins', methods=['GET'])
def view_staff_logins():
    users = auth.list_users().users
    users_data = [{"uid": user.uid, "email": user.email} for user in users]
    return jsonify(users_data), 200


if __name__ == '__main__':
    with app.app_context():  # Push an application context
        db.create_all()
    admin = Admin(app, name='I2G Admin', template_mode='bootstrap3')
    admin.add_view(AdminModelView(RefRegistration, db.session))
    admin.add_view(AdminModelView(RefJudge, db.session))
    admin.add_view(AdminModelView(RefParking, db.session))
    admin.add_view(AdminModelView(RefProject, db.session))
    admin.add_view(AdminModelView(RefRoom, db.session))
    admin.add_view(AdminModelView(TblAdmin, db.session))
    admin.add_view(AdminModelView(TblCheckIn, db.session))
    admin.add_view(AdminModelView(TblEvent, db.session))
    admin.add_view(AdminModelView(TblEventJudge, db.session))
    admin.add_view(AdminModelView(TblJudgeLogin, db.session))
    admin.add_view(AdminModelView(TblQr, db.session))

    app.run(host='0.0.0.0', port=5000, debug=True)
