from project import db
from werkzeug.security import check_password_hash


class edit_form(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    label = db.Column("label", db.String())
    required = db.Column("required", db.Boolean)
    field_type = db.Column("field_type", db.String())
    options = db.Column("options", db.String())

    def __init__(self, label, required, options, field_type):
        self.label = label
        self.required = required
        self.options = options
        self.field_type = field_type


class user(db.Model):
    id = db.Column("id", db.Integer, primary_key=True)
    first_name = db.Column("first_name", db.String())
    last_name = db.Column("last_name", db.String())
    email = db.Column("email", db.String(), unique=True)
    password = db.Column("password", db.String())
    role = db.Column("role", db.String())

    def __init__(self, first_name, last_name, email, password, role):
        self.first_name = first_name
        self.last_name = last_name
        self.email = email
        self.password = password
        self.role = role

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False

    def get_id(self):
        return self.id

    def verify_password(self, db_password, input_password):
        return check_password_hash(db_password, input_password)

    def has_role(self, role):
        return self.role == role


class event(db.Model):
    """
    Represents an event.

    Attributes:
        id (int): The unique identifier for the event.
        name (str): The name of the event.
        date (str): The date of the event.
        time (str): The time of the event.
        location (str): The location of the event.
        description (str): The description of the event.
        live (bool): Indicates if the event is live or not.
        tickets (str): The ticket information for the event.
        questions (str): The questions related to the event.

    Methods:
        __init__(name, date, time, location, description, live, tickets, questions):
            Initializes a new instance of the event class.
    """
    id = db.Column("id", db.Integer, primary_key=True)
    name = db.Column("name", db.String())
    date = db.Column("date", db.String())
    time = db.Column("time", db.String())
    location = db.Column("location", db.String())
    description = db.Column("description", db.String())
    live = db.Column("live", db.Boolean)
    tickets = db.Column("tickets", db.String())
    questions = db.Column("questions", db.String())

    def __init__(self, name, date, time, location, description, live, tickets, questions):
        self.name = name
        self.date = date
        self.time = time
        self.location = location
        self.description = description
        self.live = live
        self.tickets = tickets
        self.questions = questions


#admin 2 models 
class RefRegistration(db.Model):
    """
    Represents a registration entry in the database.

    Attributes:
        User_ID (int): The unique identifier for the user.
        First_Name (str): The first name of the user.
        Last_Name (str): The last name of the user.
        Email (str): The primary email address of the user.
        Last_Updated (str): The timestamp of the last update for the user.
        Secondary_Email (str): The secondary email address of the user.
        Secondary_Verified (int): Indicates whether the secondary email is verified (0 for not verified, 1 for verified).
        Primary_verified (int): Indicates whether the primary email is verified (0 for not verified, 1 for verified).
        Organization (str): The organization the user belongs to.
        Role (str): The role of the user.
        judges (relationship): A relationship to the RefJudge model.
        check_ins (relationship): A relationship to the TblCheckIn model.
        judge_logins (relationship): A relationship to the TblJudgeLogin model.
        qrs (relationship): A relationship to the TblQr model.
    """

    __tablename__ = 'refRegistration'
    User_ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    First_Name = db.Column(db.Text, nullable=False)
    Last_Name = db.Column(db.Text, nullable=False)
    Email = db.Column(db.Text, nullable=False, unique=True)
    Last_Updated = db.Column(db.Text, nullable=False, unique=True)
    Secondary_Email = db.Column(db.Text, nullable=True, default="n/a")
    Secondary_Verified = db.Column(db.Integer, nullable=False, default=0)
    Primary_verified = db.Column(db.Integer, nullable=False, default=1)
    Organization = db.Column(db.Text)
    Role = db.Column(db.Text)
    judges = db.relationship('RefJudge', backref='registration', lazy=True)
    check_ins = db.relationship('TblCheckIn', backref='registration', lazy=True)
    judge_logins = db.relationship('TblJudgeLogin', backref='registration', lazy=True)
    qrs = db.relationship('TblQr', backref='registration', lazy=True)

    def __repr__(self):
        return f"Class('{self.User_ID}', '{self.First_Name}', '{self.Last_Name}', '{self.Email}', '{self.Role}')"

class RefJudge(db.Model):
    """
    Represents a reference judge in the system.

    Attributes:
        ID (int): The ID of the judge (primary key).
        First_name (int): The first name of the judge.
        Last_Name (int): The last name of the judge.
        event_judges (relationship): A relationship to the TblEventJudge model.
    """
    __tablename__ = 'refJudge'
    ID = db.Column(db.Integer, db.ForeignKey('refRegistration.User_ID'), primary_key=True)
    First_name = db.Column(db.Integer, nullable=False)
    Last_Name = db.Column(db.Integer, nullable=False)
    event_judges = db.relationship('TblEventJudge', backref='judge', lazy=True)

class RefParking(db.Model):
    """
    Represents a reference parking location.

    Attributes:
        ID (int): The unique identifier for the parking location.
        Name (str): The name of the parking location.
        X_Location (str): The X-coordinate of the parking location.
        Y_Location (str): The Y-coordinate of the parking location.
    """
    __tablename__ = 'refParking'
    ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Name = db.Column(db.Text, nullable=False)
    X_Location = db.Column(db.Text, nullable=False)
    Y_Location = db.Column(db.Text, nullable=False)

class RefProject(db.Model):
    """
    Represents a reference project.

    Attributes:
        ID (int): The unique identifier for the project.
        Project_Name (str): The name of the project.
        Project_Des (str): The description of the project.
        Mentor (str): The name of the project's mentor.
        Mentor1 (int): The ID of the first mentor.
        Mentor2 (int): The ID of the second mentor.
        rooms (relationship): The rooms associated with the project.
        events (relationship): The events associated with the project.
    """
    __tablename__ = 'refProject'
    ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Project_Name = db.Column(db.Text, nullable=False)
    Project_Des = db.Column(db.Text, nullable=False)
    Mentor = db.Column(db.Text, nullable=False)
    Mentor1 = db.Column(db.Integer)
    Mentor2 = db.Column(db.Integer)
    rooms = db.relationship('RefRoom', backref='project', lazy=True)
    events = db.relationship('TblEvent', backref='project', lazy=True)

class RefRoom(db.Model):
    """
    Represents a reference room in the application.

    Attributes:
        ID (int): The unique identifier for the room.
        Name (str): The name of the room.
        Project (int): The ID of the project that the room belongs to.
        Link (str): The link associated with the room.
        events (relationship): A relationship to the TblEvent model, representing the events associated with the room.
    """
    __tablename__ = 'refRoom'
    ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Name = db.Column(db.Text, nullable=False)
    Project = db.Column(db.Integer, db.ForeignKey('refProject.ID'), nullable=False)
    Link = db.Column(db.Text, nullable=False)
    events = db.relationship('TblEvent', backref='room', lazy=True)

class TblCheckIn(db.Model):
    """
    Represents a check-in entry in the database.

    Attributes:
        ID (int): The unique identifier for the check-in entry.
        User_ID (int): The foreign key referencing the user who checked in.
        Checkin_Time (int): The timestamp of the check-in time.
        Check_Out (int): The timestamp of the check-out time (optional).
    """

    __tablename__ = 'tblCheckIn'
    ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    User_ID = db.Column(db.Integer, db.ForeignKey('refRegistration.User_ID'), unique=True, nullable=False)
    Checkin_Time = db.Column(db.Integer, nullable=False)
    Check_Out = db.Column(db.Integer)

class TblEvent(db.Model):
    """
    Represents an event in the system.

    Attributes:
        ID (int): The unique identifier for the event.
        Project_ID (int): The ID of the project associated with the event.
        Room_ID (int): The ID of the room where the event takes place.
        event_judges (list[TblEventJudge]): The list of judges associated with the event.
    """

    __tablename__ = 'tblEvent'
    ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Project_ID = db.Column(db.Integer, db.ForeignKey('refProject.ID'), nullable=False)
    Room_ID = db.Column(db.Integer, db.ForeignKey('refRoom.ID'), nullable=False)
    event_judges = db.relationship('TblEventJudge', backref='event', lazy=True)

class TblEventJudge(db.Model):
    """
    Represents a judge for an event.

    Attributes:
        ID (int): The unique identifier for the judge.
        Judge_ID (int): The foreign key referencing the judge's ID in the 'refJudge' table.
        Event_ID (int): The foreign key referencing the event's ID in the 'tblEvent' table.
        Link (str): The link associated with the judge.
        Link2 (str): Another link associated with the judge.
        Field3 (str): A field for additional information.
        Link4 (str): Yet another link associated with the judge.
    """
    __tablename__ = 'tblEventJudge'
    ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    Judge_ID = db.Column(db.Integer, db.ForeignKey('refJudge.ID'))
    Event_ID = db.Column(db.Integer, db.ForeignKey('tblEvent.ID'), nullable=False)
    Link = db.Column(db.Text, nullable=False)
    Link2 = db.Column(db.Text)
    Field3 = db.Column(db.Text)
    Link4 = db.Column(db.Text)

class TblJudgeLogin(db.Model):
    """
    Represents a judge login in the system.

    Attributes:
        ID (int): The unique identifier for the judge login.
        User_id (int): The ID of the user associated with the judge login.
        Password (str): The password for the judge login.
    """
    __tablename__ = 'tblJudgeLogin'
    ID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    User_id = db.Column(db.Integer, db.ForeignKey('refRegistration.User_ID'), unique=True, nullable=False)
    Password = db.Column(db.Text, nullable=False)

class TblQr(db.Model):
    """
    Represents a QR code in the database.

    Attributes:
        ID (int): The unique identifier for the QR code.
        User_ID (int): The foreign key referencing the user who owns the QR code.
        Value (str): The value of the QR code.
    """
    __tablename__ = 'tblQr'
    ID = db.Column(db.Integer, primary_key=True)
    User_ID = db.Column(db.Integer, db.ForeignKey('refRegistration.User_ID'), unique=True, nullable=False)
    Value = db.Column(db.Text, nullable=False, unique=True)