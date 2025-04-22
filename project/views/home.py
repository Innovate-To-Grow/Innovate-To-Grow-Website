import gspread, uuid
from threading import Thread
from flask import Blueprint, render_template, request, jsonify, redirect, url_for
from project import cache, app
import re
import json
import os
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId, json_util
from routes import CONNECTION_STRING
import uuid
from project.views.account import get_db_connection, get_email, get_access

home_blueprint = Blueprint("home", __name__, template_folder="../templates/home")

# Add this before the routes
app.jinja_env.globals['get_email'] = get_email

# Initialize MongoDB client
client = MongoClient(CONNECTION_STRING)
dbname = client['I2GUserDatabase']
curated_lists = dbname["curated_lists"]  # Use consistent collection reference

def fetch_collection(id):
    collection = curated_lists.find_one({"_id": id})
    return collection #Returns None if not found

@home_blueprint.route("/", methods=["GET", "POST"])
# @cache.cached()
def mainpage():
    return render_template("home-pre-event.html")

@home_blueprint.route("/about", methods=["GET", "POST"])
# @cache.cached()
def about():
    return render_template("about.html")

@home_blueprint.route("/privacy", methods=["GET", "POST"])
# @cache.cached()
def text_toc():
    return render_template("terms_and_conditions.html")

@home_blueprint.route("/engineering-capstone", methods=["GET", "POST"])
# @cache.cached()
def engineering_capstone():
    return render_template("engineering-capstone.html")

@home_blueprint.route("/about_EngSL", methods=["GET", "POST"])
# @cache.cached()
def about_EngSL():
    return render_template("about_EngSL.html")

@home_blueprint.route("/software-capstone", methods=["GET", "POST"])
# @cache.cached()
def software_capstone():
    return render_template("software-capstone.html")

@home_blueprint.route("/event", methods=["GET", "POST"])
# @cache.cached()
def event():
    return render_template("event.html")

@home_blueprint.route("/schedule", methods=["GET", "POST"])
# @cache.cached()
def schedule():
    return render_template("schedule.html")

@home_blueprint.route("/projects-teams", methods=["GET", "POST"])
# @cache.cached()
def projects_teams():
    return render_template("projects-teams.html")

@home_blueprint.route("/judges", methods=["GET", "POST"])
# @cache.cached()
def judges():
    return render_template("judges.html")

@home_blueprint.route("/attendees", methods=["GET", "POST"])
# @cache.cached()
def attendees():
    return render_template("attendees.html")

@home_blueprint.route("/students", methods=["GET", "POST"])
# @cache.cached()
def students():
    return render_template("students.html")

@home_blueprint.route("/acknowledgement", methods=["GET", "POST"])
# @cache.cached()
def acknowledgement():
    return render_template("acknowledgement.html")

@home_blueprint.route("/past-events", methods=["GET", "POST"])
# @cache.cached()
def past_events():
    return render_template("past-events.html")

@home_blueprint.route("/projects", methods=["GET", "POST"])
# @cache.cached()
def projects():
    return render_template("projects.html")

@home_blueprint.route("/current-projects", methods=["GET", "POST"])
# @cache.cached()
def current_projects():
    return render_template("current-projects.html")

@home_blueprint.route("/project-submission", methods=["GET", "POST"])
# @cache.cached()
def project_submission():
    return render_template("project-submission.html")

@home_blueprint.route("/sample-proposals", methods=["GET", "POST"])
# @cache.cached()
def sample_proposals():
    return render_template("sample-proposals.html")

@home_blueprint.route("/partnership", methods=["GET", "POST"])
# @cache.cached()
def partnership():
    return render_template("partnership.html")

@home_blueprint.route("/sponsorship", methods=["GET", "POST"])
# @cache.cached()
def sponsorship():
    return render_template("sponsorship.html")

@home_blueprint.route("/FAQs", methods=["GET", "POST"])
# @cache.cached()
def faq():
    return render_template("faq.html")

@home_blueprint.route("/I2G-student-agreement", methods=["GET", "POST"])
# @cache.cached()
def I2G_student_agreement():
    return render_template("I2G-student-agreement.html")

@home_blueprint.route("/ferpa", methods=["GET", "POST"])
# @cache.cached()
def ferpa():
    return render_template("ferpa.html")

@home_blueprint.route("/i2g-students-preparation", methods=["GET", "POST"])
# @cache.cached()
def i2g_students_preparation():
    return render_template("i2g-students-preparation.html")

@home_blueprint.route("/video-preparation", methods=["GET", "POST"])
# @cache.cached()
def video_preparation():
    return render_template("video-preparation.html")

@home_blueprint.route("/capstone-purchasing-reimbursement", methods=["GET", "POST"])
# @cache.cached()
def capstone_purchasing_reimbursement():
    return render_template("capstone-purchasing-reimbursement.html")

@home_blueprint.route("/contact-us", methods=["GET", "POST"])
# @cache.cached()
def contact_us():
    return render_template("contact-us.html")

@home_blueprint.route("/judging", methods=["GET", "POST"])
# @cache.cached()
def judging():
    return render_template("judging.html")

@home_blueprint.route("/template", methods=["GET", "POST"])
# @cache.cached()
def template():
    return render_template("template.html")

@home_blueprint.route("/template-email-team-students", methods=["GET", "POST"])
# @cache.cached()
def template_email_team_students():
    return render_template("template-email-team-students.html")

@home_blueprint.route("/I2G-project-sponsor-acknowledgement", methods=["GET", "POST"])
# @cache.cached()
def I2G_project_sponsor_acknowledgement():
    return render_template("I2G-project-sponsor-acknowledgement.html")

@home_blueprint.route("/home-during-event", methods=["GET", "POST"])
# @cache.cached()
def home_during_event():
    return render_template("home-during-event.html")

@home_blueprint.route("/home-post-event", methods=["GET", "POST"])
# @cache.cached()
def home_post_event():
    return render_template("home-post-event.html")

@home_blueprint.route("/2024-fall-event", methods=["GET", "POST"])
# @cache.cached()
def fall_event_2024():
    return render_template("2024-fall-event.html")

@home_blueprint.route("/2023-fall-event", methods=["GET", "POST"])
# @cache.cached()
def fall_event_2023():
    return render_template("2023-fall-event.html")

@home_blueprint.route("/2023-spring-event", methods=["GET", "POST"])
# @cache.cached()
def spring_event_2023():
    return render_template("2023-spring-event.html")
    
@home_blueprint.route("/2024-spring-event", methods=["GET", "POST"])
# @cache.cached()
def spring_event_2024():
    return render_template("2024-spring-event.html")

@home_blueprint.route("/2022-fall-event", methods=["GET", "POST"])
# @cache.cached()
def fall_event_2022():
    return render_template("2022-fall-event.html")

@home_blueprint.route("/2022-spring-event", methods=["GET", "POST"])
# @cache.cached()
def spring_event_2022():
    return render_template("2022-spring-event.html")

@home_blueprint.route("/2021-spring-event", methods=["GET", "POST"])
# @cache.cached()
def spring_event_2021():
    return render_template("2021-spring-event.html")

@home_blueprint.route("/2021-fall-event", methods=["GET", "POST"])
# @cache.cached()
def fall_event_2021():
    return render_template("2021-fall-event.html")

@home_blueprint.route("/2020-fall-post-event", methods=["GET", "POST"])
# @cache.cached()
def fall_event_post_2020():
    return render_template("2020-fall-post-event.html")

@home_blueprint.route("/2014-sponsors", methods=["GET", "POST"])
# @cache.cached()
def sponsors_2014():
    return render_template("2014-sponsors.html")

@home_blueprint.route("/2015-sponsors", methods=["GET", "POST"])
# @cache.cached()
def sponsors_2015():
    return render_template("2015-sponsors.html")

@home_blueprint.route("/past-projects", methods=["GET", "POST"])
def past_projects(uuid_string=None):
    if request.method == "POST":
        data = request.get_json()
        uuid_string = str(uuid.uuid4())
        
        # Create a MongoDB collection entry
        collection_data = {
            "_id": uuid_string,
            "userId": None,
            "title": f"Collection {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "projects": data,
            "createdAt": datetime.now().isoformat(),
        }
        
        # Insert directly into MongoDB
        curated_lists.insert_one(collection_data)
        
        return jsonify({"uuid_string": uuid_string, "collection_id": uuid_string})
    
    # For GET requests, pass only the collection ID to the template
    return render_template("past-projects.html", collection_id=uuid_string)

@home_blueprint.route('/project/<project_uuid>')
def project_detail(project_uuid):
    """View a specific project"""
    try:
        cursor = curated_lists.find({"projects.uuid": project_uuid})
        
        project_data = None
        collection = None
        
        for doc in cursor:
            for project in doc.get('projects', []):
                if project.get('uuid') == project_uuid:
                    project_data = project
                    collection = doc
                    break
            if project_data:
                break
        
        if not project_data:
            return redirect(url_for('home.past_projects'))
        
        if collection:
            collection['_id'] = str(collection['_id'])
        
        return render_template('home/project-detail.html', 
                             project_data=project_data,
                             collection=collection)
    except Exception as e:
        print(f"Error in project_detail: {str(e)}")
        return redirect(url_for('home.past_projects'))

@home_blueprint.route('/collection/<collection_id>')
def view_collection(collection_id):
    """View a specific collection"""
    if ObjectId.is_valid(collection_id):
        collection = curated_lists.find_one({"_id": ObjectId(collection_id)})
    else:
        collection = curated_lists.find_one({"_id": collection_id})
    
    if not collection:
        return redirect(url_for('home.past_projects'))
    
    collection['_id'] = str(collection['_id'])
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    total_projects = len(collection["projects"])
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    paginated_projects = collection["projects"][start_index:end_index]
    
    return render_template('collection.html', collection=collection, paginated_projects=paginated_projects, page=page, per_page=per_page, total_projects=total_projects)

@home_blueprint.route('/api/save-collection', methods=['POST'])
def save_collection():
    """API endpoint to save or update a collection in MongoDB"""

    collection_data = request.json
    
    user_id = collection_data["userId"]
    access = get_access(user_id)
    print(user_id)
    print(access)

    # Check if the collection already exists
    if "_id" in collection_data.keys():
        collection = fetch_collection(collection_data["_id"])
        if collection:
            #Update history
            history = collection.get("history", [])
            history_element = {
                "createdAt": collection["createdAt"],
                "title": collection["title"],
                "projects": collection["projects"],
                "editorContent": collection["editorContent"]
            }
            history.append(history_element)
            # Allows admins to edit main version of anyone's collection
            # Allows collection owner (user) to edit main version of their collection
            if access == "admin" or user_id == collection["userId"]:
                # Update main version of existing collection
                result = curated_lists.update_one(
                    {"_id": collection_data["_id"]},
                    {"$set": {"history": history,
                            "createdAt": collection_data["createdAt"],
                            "title": collection_data["title"],
                            "projects": collection_data["projects"],
                            "editorContent": collection_data["editorContent"]
                    }}
                )
                if result.modified_count:
                    return jsonify({"success": True, "collection_id": str(collection_data["_id"])})
                else:
                    return jsonify({"success": False, "message": "Failed to save collection."}), 500
            # Allows other users to edit a copy of the collection that is then saved in database and tied to their account
            # Allows guests to edit a copy of the collection that is then saved in database with null userId
            else:
                # Copy existing collection and save with new userId (or null if guest) and update with the made edits
                copy_collection_id = str(uuid.uuid4())
                result = curated_lists.insert_one({
                    "_id": copy_collection_id,
                    "userId": user_id,
                    "history": history,
                    "createdAt": collection_data["createdAt"],
                    "title": collection_data["title"],
                    "projects": collection_data["projects"],
                    "editorContent": collection_data["editorContent"]
                })
                redirect_url = url_for('home.past_projects') + f"?collection={copy_collection_id}"
                return jsonify({"success": True, "redirect": redirect_url})
                
        # Insert new collection
        else:
            collection_data["history"] = []
            result = curated_lists.insert_one(collection_data)
            redirect_url = url_for('home.past_projects') + f"?collection={collection_data['_id']}"
            return jsonify({"success": True, "redirect": redirect_url})
    
    else:
        return jsonify({"success": False, "message": "Missing collection ID"}), 400



@home_blueprint.route('/api/get-collection/<collection_id>', methods=['GET'])
def get_collection(collection_id):
    """Get a collection by ID from MongoDB"""
    if ObjectId.is_valid(collection_id):
        collection = curated_lists.find_one({"_id": ObjectId(collection_id)})
    else:
        collection = curated_lists.find_one({"_id": collection_id})
    
    if not collection:
        return jsonify({"success": False, "message": "Collection not found"}), 404
    
    collection['_id'] = str(collection['_id'])
    return json_util.dumps(collection)

