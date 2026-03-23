from flask import Blueprint, request, jsonify, render_template
from geopy.geocoders import Nominatim

geo_blueprint = Blueprint("geo", __name__, template_folder="../templates/geo")

seen_nodes = {}  # Store seen_nodes in memory


@geo_blueprint.route('/geo')
def home():
    return render_template('geo.html')


@geo_blueprint.route('/geo/api/process_data', methods=['POST'])
def process_data():
    global seen_nodes
    data = request.get_json()
    nodes = data['elements']
    # geolocator = Nominatim(user_agent="myGeocoder")
    for node in nodes:
        if node['id'] not in seen_nodes:
            node_type = node['tags'].get('amenity') or node['tags'].get(
                'shop') or node['tags'].get('office') or node['tags'].get(
                'building') or 'other'
            # location = geolocator.reverse((node['lat'], node['lon']))
            # address = location.address.replace(",", " ")
            # node['address'] = address
            node['type'] = node_type
            seen_nodes[node['id']] = node

    return 'Success', 200


@geo_blueprint.route('/geo/api/get_data', methods=['GET'])
def get_data():
    return jsonify(list(seen_nodes.values()))


@geo_blueprint.route('/geo/api/clear_data', methods=['POST'])
def clear_data():
    global seen_nodes
    seen_nodes = {}
    return 'Success', 200
