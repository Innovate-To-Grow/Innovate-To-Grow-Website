import gspread, uuid
from threading import Thread
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from project import cache
import re
import json
import os
from datetime import datetime

home_blueprint = Blueprint("home", __name__, template_folder="../templates/home")

# Define the path to the database file
DATABASE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'databaseMergeTable.json')

def read_database():
    # Read the database file
    if not os.path.exists(DATABASE_PATH):
        with open(DATABASE_PATH, 'w') as f:
            json.dump([], f)
        return []
        
    with open(DATABASE_PATH, 'r') as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def write_database(data):
    # Write to the database file
    with open(DATABASE_PATH, 'w') as f:
        json.dump(data, f, indent=4)

@home_blueprint.route("/", methods=["GET", "POST"])
@cache.cached()
def mainpage():
    return render_template("home-pre-event.html")
    # return render_template("home-during-event.html")
    # return render_template("home-post-event.html")
    # return render_template("home-during-semester.html")

@home_blueprint.route("/about", methods=["GET", "POST"])
@cache.cached()
def about():
    return render_template("about.html")

@home_blueprint.route("/privacy", methods=["GET", "POST"])
@cache.cached()
def text_toc():
    return render_template("terms_and_conditions.html")

@home_blueprint.route("/engineering-capstone", methods=["GET", "POST"])
@cache.cached()
def engineering_capstone():
    return render_template("engineering-capstone.html")

@home_blueprint.route("/about_EngSL", methods=["GET", "POST"])
@cache.cached()
def about_EngSL():
    return render_template("about_EngSL.html")

@home_blueprint.route("/software-capstone", methods=["GET", "POST"])
@cache.cached()
def software_capstone():
    return render_template("software-capstone.html")

@home_blueprint.route("/event", methods=["GET", "POST"])
@cache.cached()
def event():
    return render_template("event.html")

@home_blueprint.route("/schedule", methods=["GET", "POST"])
@cache.cached()
def schedule():
    return render_template("schedule.html")

@home_blueprint.route("/projects-teams", methods=["GET", "POST"])
@cache.cached()
def projects_teams():
    return render_template("projects-teams.html")

@home_blueprint.route("/judges", methods=["GET", "POST"])
@cache.cached()
def judges():
    return render_template("judges.html")

@home_blueprint.route("/attendees", methods=["GET", "POST"])
@cache.cached()
def attendees():
    return render_template("attendees.html")

@home_blueprint.route("/students", methods=["GET", "POST"])
@cache.cached()
def students():
    return render_template("students.html")

@home_blueprint.route("/acknowledgement", methods=["GET", "POST"])
@cache.cached()
def acknowledgement():
    return render_template("acknowledgement.html")

@home_blueprint.route("/past-events", methods=["GET", "POST"])
@cache.cached()
def past_events():
    return render_template("past-events.html")

@home_blueprint.route("/projects", methods=["GET", "POST"])
@cache.cached()
def projects():
    return render_template("projects.html")

@home_blueprint.route("/current-projects", methods=["GET", "POST"])
@cache.cached()
def current_projects():
    return render_template("current-projects.html")

@home_blueprint.route("/project-submission", methods=["GET", "POST"])
@cache.cached()
def project_submission():
    return render_template("project-submission.html")

@home_blueprint.route("/sample-proposals", methods=["GET", "POST"])
@cache.cached()
def sample_proposals():
    return render_template("sample-proposals.html")

@home_blueprint.route("/partnership", methods=["GET", "POST"])
@cache.cached()
def partnership():
    return render_template("partnership.html")

@home_blueprint.route("/sponsorship", methods=["GET", "POST"])
@cache.cached()
def sponsorship():
    return render_template("sponsorship.html")

@home_blueprint.route("/FAQs", methods=["GET", "POST"])
@cache.cached()
def faq():
    return render_template("faq.html")

@home_blueprint.route("/I2G-student-agreement", methods=["GET", "POST"])
@cache.cached()
def I2G_student_agreement():
    return render_template("I2G-student-agreement.html")

@home_blueprint.route("/ferpa", methods=["GET", "POST"])
@cache.cached()
def ferpa():
    return render_template("ferpa.html")

@home_blueprint.route("/i2g-students-preparation", methods=["GET", "POST"])
@cache.cached()
def i2g_students_preparation():
    return render_template("i2g-students-preparation.html")

@home_blueprint.route("/video-preparation", methods=["GET", "POST"])
@cache.cached()
def video_preparation():
    return render_template("video-preparation.html")

@home_blueprint.route("/capstone-purchasing-reimbursement", methods=["GET", "POST"])
@cache.cached()
def capstone_purchasing_reimbursement():
    return render_template("capstone-purchasing-reimbursement.html")

@home_blueprint.route("/contact-us", methods=["GET", "POST"])
@cache.cached()
def contact_us():
    return render_template("contact-us.html")

@home_blueprint.route("/judging", methods=["GET", "POST"])
@cache.cached()
def judging():
    return render_template("judging.html")

@home_blueprint.route("/template", methods=["GET", "POST"])
@cache.cached()
def template():
    return render_template("template.html")

@home_blueprint.route("/template-email-team-students", methods=["GET", "POST"])
@cache.cached()
def template_email_team_students():
    return render_template("template-email-team-students.html")

@home_blueprint.route("/I2G-project-sponsor-acknowledgement", methods=["GET", "POST"])
@cache.cached()
def I2G_project_sponsor_acknowledgement():
    return render_template("I2G-project-sponsor-acknowledgement.html")

@home_blueprint.route("/home-during-event", methods=["GET", "POST"])
@cache.cached()
def home_during_event():
    return render_template("home-during-event.html")

@home_blueprint.route("/home-post-event", methods=["GET", "POST"])
@cache.cached()
def home_post_event():
    return render_template("home-post-event.html")

@home_blueprint.route("/2024-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2024():
    return render_template("2024-fall-event.html")

@home_blueprint.route("/2023-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2023():
    return render_template("2023-fall-event.html")

@home_blueprint.route("/2023-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2023():
    return render_template("2023-spring-event.html")
    
@home_blueprint.route("/2024-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2024():
    return render_template("2024-spring-event.html")

@home_blueprint.route("/2022-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2022():
    return render_template("2022-fall-event.html")

@home_blueprint.route("/2022-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2022():
    return render_template("2022-spring-event.html")

@home_blueprint.route("/2021-spring-event", methods=["GET", "POST"])
@cache.cached()
def spring_event_2021():
    return render_template("2021-spring-event.html")

@home_blueprint.route("/2021-fall-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_2021():
    return render_template("2021-fall-event.html")

@home_blueprint.route("/2020-fall-post-event", methods=["GET", "POST"])
@cache.cached()
def fall_event_post_2020():
    return render_template("2020-fall-post-event.html")

@home_blueprint.route("/2014-sponsors", methods=["GET", "POST"])
@cache.cached()
def sponsors_2014():
    return render_template("2014-sponsors.html")

@home_blueprint.route("/2015-sponsors", methods=["GET", "POST"])
@cache.cached()
def sponsors_2015():
    return render_template("2015-sponsors.html")

@home_blueprint.route("/past-projects", methods=["GET", "POST"])
@home_blueprint.route("/past-projects/<uuid_string>", methods=["GET", "POST"])
def past_projects(uuid_string=None):
    wks = gspread.service_account().open("Shareable Merge Tables").worksheet("Sheet1")
    if request.method == "POST":
        data = request.get_json()
        uuid_string = str(uuid.uuid4())
        
        def update_sheet():
            team_name = ""
            team_number = ""

            for d in data[:-1]:
                team_name += d["Team Name"] + " ; "
                team_number += d["Team#"] + " ; "

            if len(data) > 0:
                team_name += data[-1]["Team Name"] 
                team_number += data[-1]["Team#"] 
            
            wks.append_row(values=[uuid_string, team_name, team_number])

        Thread(target=update_sheet).start()
        
        return jsonify({"uuid_string": uuid_string})
       
    team_names = []
    team_numbers = []

    if uuid_string is not None:
        cell = wks.find(uuid_string, in_column=1)
        if cell is not None:
            query = wks.row_values(cell.row)
            if len(query) == 3:
                team_names = query[1].split(" ; ")
                team_numbers = query[2].split(" ; ")
    
    return render_template("past-projects.html", team_names=team_names, team_numbers=team_numbers)

@home_blueprint.route('/api/save-project', methods=['POST'])
def save_project():
    """API endpoint to save project data to JSON database"""
    project_data = request.json
    
    # Read current database
    database = read_database()
    
    # Check if project already exists
    project_exists = False
    for i, project in enumerate(database):
        if project.get('uuid') == project_data.get('uuid'):
            database[i] = project_data
            project_exists = True
            break
    
    # If project doesn't exist, add it
    if not project_exists:
        database.append(project_data)
    
    # Save updated database
    write_database(database)
    
    return jsonify({"success": True})

@home_blueprint.route('/project/<project_uuid>')
def project_detail(project_uuid):
    """Render the project detail page for a specific project"""
    collection_id = request.args.get('collection')
    
    # Read the database
    database = read_database()
    
    # Find the project
    project_data = None
    collection_data = None
    
    if collection_id:
        # Look for the project in the specified collection
        for collection in database:
            if collection.get('_id') == collection_id:
                collection_data = collection
                for project in collection.get('projects', []):
                    if project.get('uuid') == project_uuid:
                        project_data = project
                        break
                if project_data:
                    break
    else:
        # No collection specified, search all collections
        for collection in database:
            for project in collection.get('projects', []):
                if project.get('uuid') == project_uuid:
                    project_data = project
                    collection_data = collection
                    break
            if project_data:
                break
    
    # If project found, render the template
    if project_data:
        return render_template('home/project-detail.html', 
                               project_data=project_data, 
                               collection=collection_data)
    
    # If project not found, redirect to projects list
    return redirect(url_for('home.past_projects'))

@home_blueprint.route('/past-projects/<project_uuid>')
def legacy_project_detail(project_uuid):
    """Redirect from old URL format to new one"""
    return redirect(url_for('home.project_detail', project_uuid=project_uuid))

@home_blueprint.route('/api/save-collection', methods=['POST'])
def save_collection():
    """API endpoint to save a collection"""
    collection_data = request.json
    
    # Read current database
    database = read_database()
    
    # Check if collection already exists
    collection_exists = False
    for i, collection in enumerate(database):
        if collection.get('_id') == collection_data.get('_id'):
            database[i] = collection_data
            collection_exists = True
            break
    
    # If collection doesn't exist, add it
    if not collection_exists:
        database.append(collection_data)
    
    # Save updated database
    write_database(database)
    
    return jsonify({"success": True, "collection_id": collection_data.get('_id')})

@home_blueprint.route('/api/get-latest-collection', methods=['GET'])
def get_latest_collection():
    """API endpoint to get the most recently created collection"""
    database = read_database()
    
    if not database:
        return jsonify({"success": False, "message": "No collections found"})
    
    # Sort collections by createdAt timestamp (newest first)
    sorted_collections = sorted(database, key=lambda x: x.get('createdAt', ''), reverse=True)
    
    return jsonify({"success": True, "collection": sorted_collections[0] if sorted_collections else None})

@home_blueprint.route('/api/add-project-to-collection/<collection_id>', methods=['POST'])
def add_project_to_collection(collection_id):
    """API endpoint to add a project to a collection"""
    project_data = request.json
    
    # Read database
    database = read_database()
    
    # Find the collection
    collection_found = False
    for i, collection in enumerate(database):
        if collection.get('_id') == collection_id:
            # Check if project already exists in collection
            project_exists = False
            for j, project in enumerate(collection.get('projects', [])):
                if project.get('uuid') == project_data.get('uuid'):
                    # Update existing project
                    collection['projects'][j] = project_data
                    project_exists = True
                    break
            
            # Add project if it doesn't exist
            if not project_exists:
                if 'projects' not in collection:
                    collection['projects'] = []
                collection['projects'].append(project_data)
            
            # Update lastUpdated timestamp
            collection['lastUpdated'] = datetime.now().isoformat()
            
            database[i] = collection
            collection_found = True
            break
    
    if not collection_found:
        return jsonify({"success": False, "message": "Collection not found"})
    
    # Save updated database
    write_database(database)
    
    return jsonify({"success": True})

@home_blueprint.route('/collection/<collection_id>')
def view_collection(collection_id):
    """Render the collection view page"""
    # Read database
    database = read_database()
    
    # Find the collection
    collection = None
    for coll in database:
        if coll.get('_id') == collection_id:
            collection = coll
            break
    
    if not collection:
        return redirect(url_for('home.past_projects'))  # Changed from home_blueprint.past_projects
    
    return render_template('home/collection.html', collection=collection)
