from wtforms import Form, StringField, SelectField, RadioField, IntegerField, SubmitField, validators, SelectMultipleField, widgets

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()
    
class RegistrationForm(Form):
    first_name = StringField('First Name', [validators.InputRequired(' ')])
    last_name = StringField('Last Name', [validators.InputRequired(' ')])
    primary_email = StringField('Primary Email Address', 
                                [validators.InputRequired(' '),
                                validators.Email()])
    confirm_primary = StringField('Confirm Primary Email',
                                [validators.InputRequired(' '),
                                validators.EqualTo('primary_email', message = 'Must match primary email')])
    secondary_email = StringField('Secondary Email Address', 
                                [validators.InputRequired(' '),
                                validators.Email()])
    confirm_secondary = StringField('Confirm Secondary Email',
                                [validators.InputRequired(' '),
                                validators.EqualTo('secondary_email', message = 'Must match secondary email')])
    submit = SubmitField('Submit')
    


class InformationForm(Form):
    city = StringField('City *', 
                                [validators.InputRequired(' ')])

    state = SelectField('State (Applicable to US and Canada) *', 
                                [validators.InputRequired(' ')],
                                choices = [('N/A','Not Applicable'),('AL','Alabama'),('AK','Alaska'),('AZ','Arizona'),('AR','Arkansas'),
                                ('CA','California'),('CO','Colorado'),('CT','Connecticut'),('DE','Delaware'),('FL','Florida'),('GA','Georgia'),
                                ('HI','Hawaii'),('ID','Idaho'),('IL','Illinois'),('IN','Indiana'),('IA','Iowa'),('KS','Kansas'),
                                ('KY','Kentucky'),('LA','Louisiana'),('ME','Maine'),('MD','Maryland'),('MA','Massachusetts'),
                                ('MI','Michigan'),('MN','Minnesota'),('MS','Mississippi'),('MO','Missouri'),('MT','Montana'),('NE','Nebraska'),
                                ('NV','Nevada'),('NH','New Hampshire'),('NJ','New Jersey'),('NM','New Mexico'),('NY','New York'),
                                ('NC','North Carolina'),('ND','North Dakota'),('OH','Ohio'),('OK','Oklahoma'),('OR','Oregon'),
                                ('PA','Pennsylvania'),('RI','Rhode Island'),('SC','South Carolina'),('SD','South Dakota'),
                                ('TN','Tennessee'),('TX','Texas'),('UT','Utah'),('VT','Vermont'),('VA','Virginia'),
                                ('WA','Washington'),('WV','West Virginia'),('WI','Wisconsin'),('WY','Wyoming'),
                                ('AB','Alberta'),('BC','British Columbia'),('MB','Manitoba'),('NB','New Brunswick'),
                                ('NL','Newfoundland and Labrador'),('NT','Northwest Territories'),('NS','Nova Scotia'),
                                ('NU','Nunavut'),('ON','Ontario'),('PE','Prince Edward Island'),('QC','Quebec'),
                                ('SK','Saskatchewan'),('YT','Yukon')]) 


    zipcode = IntegerField('Zip Code *', 
                                [validators.InputRequired(' ')])

    country = SelectField('Country *', 
                                [validators.InputRequired(' ')],
                                choices=['Canada','Italy','USA','Other'])

    country_other = StringField('If you chose Other above please explain',
                                [validators.Optional(strip_whitespace=True)])

    organization = StringField('Organization *', 
                                [validators.InputRequired(' ')])

    school = StringField('School / Institute / Center',
                                [validators.Optional(strip_whitespace=True)])

    division = StringField('Division / Department',
                                [validators.Optional(strip_whitespace=True)])

    position = StringField('Position (last or current) *', 
                                [validators.InputRequired(' ')])

    discipline = SelectField('Discipline *', 
                                [validators.InputRequired(' ')], 
                                choices=['Arts & Humanities: American Studies','Arts & Humanities: Classics',
                                'Arts & Humanities: Comparative Literature','Arts & Humanities: Feminist and Gender and Sexuality Studies',
                                'Arts & Humanities: Film Studies','Arts & Humanities: History','Arts & Humanities: History of Art and Architecture and Archaeology',
                                'Arts & Humanities: Language and Literature - English','Arts & Humanities: Language and Literature - French','Arts & Humanities: Language and Literature - German',
                                'Arts & Humanities: Language and Literature - Italian','Arts & Humanities: Language and Literature - Spanish','Arts & Humanities: Language and Literature - Other',
                                'Arts & Humanities: Music Studies','Arts & Humanities: Philosophy','Arts & Humanities: Race and Ethnicity and post-Colonial Studies',
                                'Arts & Humanities: Religion','Arts & Humanities: Rhetoric and Composition','Arts & Humanities: Theater and Performance Studies',
                                'Arts & Humanities: Visual Arts','Arts & Humanities: Other','Engineering: Aerospace Engineering','Engineering: Biomedical Engineering & Bioengineering',            
                                'Engineering: Chemical Engineering','Engineering: Civil and Environmental Engineering','Engineering: Computational Engineering',
                                'Engineering: Computer Engineering','Engineering: Electrical Engineering','Engineering: Information Science','Engineering: Materials Science and Engineering',
                                'Engineering: Mechanical Engineering','Engineering: Operations Research and Systems Eng. and Industrial Eng.','Engineering: Nanoscience and Nanotechnology',
                                'Engineering: Nuclear Engineering','Engineering: Other','Life Sciences: Animal Sciences','Life Sciences: Biochemistry and Biophysics and Structural Biology',
                                'Life Sciences: Bioinformatics','Life Sciences: Biotechnology','Life Sciences: Cell and Developmental Biology',
                                'Life Sciences: Ecology and Evolutionary Biology','Life Sciences: Entomology','Life Sciences: Genetics and Genomics',
                                'Life Sciences: Food Science','Life Sciences: Forestry and Forest Sciences','Life Sciences: Immunology and Infectious Disease',
                                'Life Sciences: Kinesiology','Life Sciences: Medicine','Life Sciences: Microbiology','Life Sciences: Neuroscience and Neurobiology',
                                'Life Sciences: Nursing','Life Sciences: Nutrition','Life Sciences – Pharmacology and Toxicology and Environmental Health',
                                'Life Sciences: Physiology','Life Sciences: Plant Sciences','Life Sciences: Public Health','Life Sciences: Systems Biology',
                                'Life Sciences: Other','Physical Sciences & Mathematics: Applied Mathematics','Physical Sciences & Mathematics: Astrophysics and Astronomy',
                                'Physical Sciences & Mathematics: Chemistry','Physical Sciences & Mathematics: Computer Sciences','Physical Sciences & Mathematics: Earth Sciences',
                                'Physical Sciences & Mathematics: Mathematics','Physical Sciences & Mathematics: Oceanography and Atmospheric Sciences and Meteorology','Physical Sciences & Mathematics: Physics',
                                'Physical Sciences & Mathematics: Statistics and Probability','Physical Sciences & Mathematics: Other','Social & Behavioral Sciences: Agricultural and Resource Economics',
                                'Social & Behavioral Sciences: Anthropology','Social & Behavioral Sciences: Business','Social & Behavioral Sciences: Communication',
                                'Social & Behavioral Sciences: Criminology and Criminal Justice','Social & Behavioral Sciences: Economics','Social & Behavioral Sciences: Geography',
                                'Social & Behavioral Sciences: Law','Social & Behavioral Sciences: Linguistics','Social & Behavioral Sciences: Political Science',
                                'Social & Behavioral Sciences: Psychology','Social & Behavioral Sciences: Public Affairs and Public Policy and Public Administration','Social & Behavioral Sciences: Science and Technology Studies',
                                'Social & Behavioral Sciences: Sociology','Social & Behavioral Sciences: Urban Studies and Planning','Social & Behavioral Sciences: Other'])

    discipline_other = StringField('If you chose Other above please explain',
                                [validators.Optional(strip_whitespace=True)])

    specialty = StringField('Specialty *', 
                                [validators.InputRequired(' ')])

    education = SelectField('Highest Degree *', 
                                [validators.InputRequired(' ')],
                                choices=['Laurea','Laurea Triennale','Laurea Magistrale','Bachelor',
                                'Master','JD','MBA','MD','MD PhD',
                                'PhD','Other'])

    education_other = StringField('If you chose Other above please explain',
                                [validators.Optional(strip_whitespace=True)])

    education_year = StringField('Year (highest degree) *', 
                                [validators.InputRequired(' ')])

    alma_mater = StringField('Alma Mater (highest degree) *', 
                                [validators.InputRequired(' ')])

    alma_mater_italy = StringField('Alma Mater in Italy',
                                [validators.Optional(strip_whitespace=True)])

    linkedin = StringField('LinkedIn profile',
                                [validators.Optional(strip_whitespace=True)])

    researchgate = StringField('ResearchGate profile',
                                [validators.Optional(strip_whitespace=True)])

    webpage = StringField('Webpage',
                                [validators.Optional(strip_whitespace=True)])

    '''
    reasons = MultiCheckboxField('Reasons to join *',  
                                choices=['Young ISSNAF','Membership','Communication','Development',
                                'Events','Not interested','Other'])

    reasons_other = StringField('If you chose Other above please explain',
                                [validators.Optional(strip_whitespace=True)])

    volunteering = MultiCheckboxField('Volunteering *', 
                                [validators.InputRequired(' ')], 
                                choices=['Education','Get career advice','Give back','Networking','Other'])

    volunteering_other = StringField('If you chose Other above please explain',
                                [validators.Optional(strip_whitespace=True)])
    '''

    comments = StringField('Comments',
                                [validators.Optional(strip_whitespace=True)])

    affiliation = SelectField('Membership/Affiliation *', 
                                [validators.InputRequired(' ')], 
                                choices=['Member','Affiliate'])

    submit = SubmitField('Submit')
