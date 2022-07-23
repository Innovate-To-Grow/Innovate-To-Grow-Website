class member_roster:
    def __init__(self, id, first_name, last_name, primary_email, secondary_email, primary_email_status, secondary_email_status, info_completed, organization=None, phonenumber=None, titlerole=None):
        self.id = id
        self.first_name = first_name
        self.last_name = last_name
        self.primary_email = primary_email
        self.secondary_email = secondary_email
        self.primary_email_status = primary_email_status
        self.secondary_email_status = secondary_email_status
        self.info_completed = info_completed
        self.organization = organization
        self.phonenumber = phonenumber
        self.titlerole = titlerole

    def is_authenticated(self):
        return True

    def is_active(self):
        return True

    def is_anonymous(self):
        return False
    
    def get_id(self):
        return self.id

# class member_data(db.Model):
#     id = db.Column("id", db.Integer, primary_key=True)
#     user_key = db.Column("user_key", db.Integer)
#     city = db.Column("city", db.String(255)) 
#     state = db.Column("state", db.String(255))
#     zip_code = db.Column("zip_code", db.Integer)
#     country = db.Column("country", db.String(255))
#     country_other = db.Column("country_other", db.String(255))
#     organization = db.Column("organization", db.String(255))
#     school = db.Column("school", db.String(255))
#     department = db.Column("department", db.String(255))
#     position = db.Column("position", db.String(255))
#     discipline = db.Column("discipline", db.String(255))
#     discipline_other = db.Column("discipline_other", db.String(255))
#     specialty = db.Column("specialty", db.String(255))
#     highest_degree = db.Column("highest_degree", db.String(255))
#     highest_degree_other = db.Column("highest_degree_other", db.String(255))
#     graduation_date = db.Column("graduation_date", db.String(255))
#     alma_mater = db.Column("alma_mater", db.String(255))
#     alma_mater_italy = db.Column("alma_mater_italy", db.String(255))
#     linked_in = db.Column("linked_in", db.String(255))
#     research_gate = db.Column("research_gate", db.String(255))
#     webpage = db.Column("webpage", db.String(255))
#     comments = db.Column("comments", db.String(555))
#     member_type = db.Column("member_type", db.String(255))


#     def __init__(self, user_key, city, state, zip_code, country, country_other, organization, school, department, 
#     position, discipline, discipline_other, specialty, highest_degree, highest_degree_other, graduation_date, 
#     alma_mater, alma_mater_italy, linked_in, research_gate, webpage, comments, member_type):
#         self.user_key = user_key
#         self.city = city
#         self.state = state
#         self.zip_code = zip_code
#         self.country = country
#         self.country_other = country_other
#         self.organization = organization
#         self.school = school
#         self.department = department 
#         self.position = position
#         self.discipline = discipline
#         self.discipline_other = discipline_other
#         self.specialty = specialty
#         self.highest_degree = highest_degree
#         self.highest_degree_other = highest_degree_other
#         self.graduation_date = graduation_date
#         self.alma_mater = alma_mater
#         self.alma_mater_italy = alma_mater_italy      
#         self.linked_in = linked_in
#         self.research_gate = research_gate
#         self.webpage = webpage
#         self.comments = comments
#         self.member_type = member_type