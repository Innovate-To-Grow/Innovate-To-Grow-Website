import sqlite3
import json
import googlemaps
import requests
##from googleplaces import GooglePlaces, types, lang
from sqlalchemy import null
from math import isclose
import numpy as np

from sqlalchemy import null

APIkey = '***REMOVED_GOOGLE_API_KEY***'
gmaps = googlemaps.Client(key = APIkey)

class DBClass():
    def __init__(self):
        self.coordinates = []
        self.coordinate_array = []      #[{"lat1": latitude1, "long1": longitude1, "lat2": latitude2, "long2":longitude2},  ....]
        self.area_id = 0
        self.composite_id = 0
        new_area = self.access_most_recent_area()
        # print("New area: ", new_area)
        if new_area != 0:
            self.area_id = new_area[0] + 1
        new_composite = self.access_most_recent_composite()
        # print("New composite: ", new_composite)
        if new_composite != 0:
            self.composite_id = new_composite[0] + 1
            self.save_composite_to_db("Current Search")
        else:
            self.save_composite_to_db("Current Search")
        #print(str(self.area_id) + " " + str(self.composite_id))
    
    
    def disp_internal(self):
        pass
        # print("coordinates: ", self.coordinates)
        # print("coordinates Array: ", self.coordinate_array)
        # print("Area ID: ", self.area_id)
        # print("Composite_ID: ", self.composite_id)
        
        
    def get_db_connect(self):
        """ Attempts to create a connection to the database
        Returns:
            sqlite3 connection: returns the sqlite connection or none if error
        """
        connection = None
        # try:
        connection = sqlite3.connect(
            "project/db/data.sqlite3")
        # except sqlite3.error as e:
        #     print(e)
        return connection

    def dict_factory(self, cursor, row):
        """ Converts row_factory function to output dictionaries instead of tuples
        Args:
            cursor (_type_):s Database Cursor
            row (_type_): Row of database
        Returns:
            dict: returns a dictionary of values with column names as keys
        """
        return dict((cursor.description[idx][0], value) for idx, value in enumerate(row))

    def composite_logic(self):
        """ Logic function that uses the shape_querying function to find POI in composite areas
        Returns:
            list: list of data to be displayed on datatable
        """
        # print(self.coordinate_array)
        data_to_send = []
        for i in self.coordinate_array:
            datas = self.shape_querying(i)
            for j in range(len(datas)):
                if datas[j] not in data_to_send:
                    data_to_send.append(datas[j])
        return data_to_send
    
    
    def save_area_to_temp(self, data):
        """ Takes the data coordinate received and resturctures them and then stores them into the temporary storage self.coodinate_array.

        Args:
            data (JSON/Dictionary): Rectangle area coordinates 
        """
        latitude1 = data['testcoordNE[lat]']    #assign to latitude1
        longitude1 = data['testcoordNE[lng]']   #assign to longitude1
        latitude2 = data['testcoordSW[lat]']    #assign to latitude2
        longitude2 = data['testcoordSW[lng]']   #assign to longitude2
        coordinates = {"lat1": latitude1, "long1": longitude1, "lat2": latitude2, "long2":longitude2}
        self.coordinate_array.append(coordinates)
    
    
    def save_area_to_db(self, data):
        """ Takes the coodrinate data and saves them to the database. It also stores the coodinates into the temporary storage self.coodinate_array.
 
        Args:
            data (JSON/Dictionary):  Rectangle area coordinates 

        Returns:
            String: Lets the user know that it has been saved.
        """
        # print("saving to db")
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute('''pragma foreign_keys = ON''')
        connection.commit()
        latitude1 = data['testcoordNE[lat]']    #assign to latitude1
        longitude1 = data['testcoordNE[lng]']   #assign to longitude1
        latitude2 = data['testcoordSW[lat]']    #assign to latitude2
        longitude2 = data['testcoordSW[lng]']   #assign to longitude2
        self.area_id += 1
        cursor.execute('''INSERT INTO areas(area_id, latitude1, longitude1, latitude2, longitude2, composite_id) VALUES(?,?,?,?,?,?)
                        ''', (self.area_id, latitude1, longitude1, latitude2, longitude2, self.composite_id))
        connection.commit()
        coordinates = {"lat1": latitude1, "long1": longitude1, "lat2": latitude2, "long2":longitude2}
        self.coordinate_array.append(coordinates)
        return "Saved Successfully"
    

    def delete_area_from_db_coords(self, data):
        # print("deleting from coords")
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute('''pragma foreign_keys = ON''')
        connection.commit()
        latitude1 = data['testcoordNE[lat]']    #assign to latitude1
        longitude1 = data['testcoordNE[lng]']   #assign to longitude1
        latitude2 = data['testcoordSW[lat]']    #assign to latitude2
        longitude2 = data['testcoordSW[lng]']   #assign to longitude2
        cursor.execute('''DELETE FROM areas WHERE latitude1 LIKE ? AND longitude1 LIKE ? AND latitude2 LIKE ? AND longitude2 LIKE ? 
                        AND composite_id = ?;
                        ''', (latitude1, longitude1, latitude2, longitude2, self.composite_id))
        connection.commit()
        coordinates = {"lat1": latitude1, "long1": longitude1, "lat2": latitude2, "long2":longitude2}
        
        coord_array_holder = self.coordinate_array
        
        # print(coordinates)
        for i in range(0, len(coord_array_holder)):
            # print(self.dict_compare(coord_array_holder[i], coordinates))
            if self.dict_compare(coord_array_holder[i], coordinates):
                # print(i)
                coord_array_holder.pop(i)
                break
        
        self.coordinate_array = coord_array_holder
        return ""

    def dict_compare(self, dict1, dict2):
        # print(dict1)
        dict1_val =  [float(i)for i in list(dict1.values())] 
        dict2_val = [float(i)for i in list(dict2.values())] 
        # print(dict1_val, dict2_val)

        for i in range(0, len(dict1_val)):
            if isclose(dict1_val[i], dict2_val[i], rel_tol=0.1) == False:
                return False
            else:
                return True
            
            
    def access_most_recent_composite(self):
        # print("most recent composite")
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute(
            '''SELECT * FROM composites WHERE composite_id = (SELECT MAX(composite_id) FROM composites)''')
        composites = cursor.fetchone()
        if composites == None:
            # print("No searches yet")
            return 0
        #print(composites)
        return composites    
    
    
    def access_most_recent_area(self):
        # print("most recent area")
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute(
            '''SELECT * FROM areas WHERE area_id = (SELECT MAX(area_id) FROM areas)''')
        area = cursor.fetchone()
        # area = dict(area_id = row[0], lat1 = row[1], long1 = row[2], lat2 = row[3], long2 = row[4], composite_id = row[5])
        # print(area)
        if area == None:
            # print("No areas yet")
            return 0
        # print("Accessed most recent area")
        return area
    
    
    def load_areas_from_composite(self, composite_id):
        connection = self.get_db_connect()
        connection.row_factory = self.dict_factory
        cursor = connection.cursor()
        cursor.execute('''pragma foreign_keys = ON''')
        connection.commit()
        cursor.execute('''SELECT * FROM areas WHERE composite_id = ?''', (composite_id,))
        output_data = cursor.fetchall()

        self.coordinate_array=[]
        for coordinate in output_data: 
             coordinates_to_array = {"lat1": coordinate[1], "long1": coordinate[2], "lat2": coordinate[3], "long2":coordinate[4]}
             self.coordinate_array.append(coordinates_to_array)
             
        self.composite_logic()

        return output_data


    def load_composites_from_user(self, user_id):
        connection = self.get_db_connect()
        connection.row_factory = self.dict_factory
        cursor = connection.cursor()
        cursor.execute('''pragma foreign_keys = ON''')
        connection.commit()
        cursor.execute('''SELECT * FROM composites WHERE user_id = ?''', (user_id,))
        output_data = cursor.fetchall()
        return output_data


    def delete_all_areas_from_db(self):
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM areas WHERE composite_id = ?", (self.composite_id,))
        connection.commit()
        self.coordinate_array = []


    def delete_area_from_db(self, id):
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM areas WHERE area_id = ?", (id,))
        connection.commit()
    
    
    def delete_composites_from_db(self, id):
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute("DELETE FROM areas WHERE composite_id = ?", (id,))
        connection.commit()
        cursor.execute("DELETE FROM composites WHERE composite_id = ?", (id,))
        connection.commit()

        
    def rename_composite_to_db(self, name):
        # print("really renaming/updating name to db")
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute('''pragma foreign_keys = ON''')
        connection.commit()
        cursor.execute('''UPDATE composites SET composite_name = ? WHERE (composite_id = ? AND user_id = ?)
                        ''', (name, self.composite_id, 0))
        self.composite_id += 1
        connection.commit()
        self.save_composite_to_db("Current Search")
        return ""

    def save_composite_to_db(self, name):
        # print("saving to db")
        connection = self.get_db_connect()
        cursor = connection.cursor()
        cursor.execute('''pragma foreign_keys = ON''')
        connection.commit()
        cursor.execute('''INSERT INTO composites(composite_id, composite_name, user_id) VALUES(?,?,?)
                        ''', (self.composite_id, name, 0))
        connection.commit()
        return ""

    def shape_querying(self, latestcoords):
        connection = self.get_db_connect()
        connection.row_factory = self.dict_factory
        cursor = connection.cursor()

        cursor.execute('''
        SELECT *
        FROM businesses
        WHERE latitude < ? AND latitude > ? AND longitude > ? AND longitude < ?
        ''', (latestcoords["lat1"], latestcoords["lat2"], latestcoords["long2"], latestcoords["long1"]))

        # # latitude of rectangle is less than the northeastern latitude and greater than southwestern latitude
        # # longitude of rectangle is greater than the southwestern and and less than northeastern longitude

        output_data = cursor.fetchall()
        # print(">>>>>> Shape Querying Functions")

        # print(latestcoords["lat1"], "lat1")
        # print(latestcoords["lat2"], "lat2")
        # print(latestcoords["long1"], "long1")
        # print(latestcoords["long2"], "long2")
        # print((float(latestcoords["lat1"]) + float(latestcoords["lat2"]))/2)
        # print((float(latestcoords["long1"]) + float(latestcoords["long2"]))/2)
        lat = (float(latestcoords["lat1"]) + float(latestcoords["lat2"]))/2
        long = (float(latestcoords["long1"]) + float(latestcoords["long2"]))/2
        rad = abs((float(latestcoords["lat1"]) - float(latestcoords["lat2"]))/2)
        rad = rad * 111139
        # print(rad)

        url = ("https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=" +  str(lat) +  "," + str(long) + "&radius="+ str(rad) +"&key=" + APIkey + "")

        # print(url)

        payload = {} 
        headers = {}
 
        response = requests.request("GET", url, headers=headers, data=payload)

        ##print(response.text)

        response_dict = json.loads(response.text)

        stored_results = []
        try:
            nextpage = response_dict['next_page_token']
        except:
            nextpage = "none"

        for place in response_dict['results']:
            my_place_id = place['place_id']
            my_fields = ['name', 'formatted_address']
            places_details = gmaps.place(place_id = my_place_id, fields = my_fields)
            # print(places_details['result'])
            ##places_details['result']["address"] = places_details['result'].pop("formatted_address")
            stored_results.append(places_details['result'])  

            ##print(stored_results)


        url = ("https://maps.googleapis.com/maps/api/place/nearbysearch/json?pagetoken=" + nextpage + "&key=" + APIkey + "")
        # print(url)

        payload = {}
        headers = {}

        response = requests.request("GET", url, headers=headers, data=payload)

        response_dict = json.loads(response.text)

        try:
            nextpage = response_dict['next_page_token']
        except:
            nextpage = "none"
            
        for place in response_dict['results']:
            my_place_id = place['place_id']
            my_fields = ['name', 'formatted_address']
            places_details = gmaps.place(place_id = my_place_id, fields = my_fields)
            # print(places_details['result'])
            ##places_details['result']["address"] = places_details['result'].pop("formatted_address")
            stored_results.append(places_details['result'])

        url = ("https://maps.googleapis.com/maps/api/place/nearbysearch/json?pagetoken=" + nextpage + "&key=" + APIkey + "")
        # print(url)
            
        payload = {}
        headers = {}

        response = requests.request("GET", url, headers=headers, data=payload)

        response_dict = json.loads(response.text)

        for place in response_dict['results']:
            my_place_id = place['place_id']
            my_fields = ['name', 'formatted_address']
            places_details = gmaps.place(place_id = my_place_id, fields = my_fields)
            # print(places_details['result'])
            ##places_details['result']["address"] = places_details['result'].pop("formatted_address")
            stored_results.append(places_details['result'])

        ##print(stored_results)
        ##print(output_data)

        return stored_results