let tags = ["aerialway", "aeroway", "amenity", "boundary", "building", "craft", "emergency", "geological", "healthcare", "historic", "landuse", "leisure", "man_made", "military", "natural", "office", "place", "public_transport", "route", "shop", "sport", "telecom", "tourism", "water", "waterway"]

let map = L.map('map').setView([37.3616569, -120.4326071], 13);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png').addTo(map);

let drawnItems = new L.FeatureGroup();
map.addLayer(drawnItems);

let drawControl = new L.Control.Draw({
    draw: {
        polygon: true,
        polyline: false,
        circle: true,
        marker: false,
        circlemarker: false,
        rectangle: true,
    },
    edit: {
        featureGroup: drawnItems
    }
});
map.addControl(drawControl);

// let overpassQuery = `[out:json][timeout:25];(node["${tags[i]}"](${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}););out body;>;out skel qt;`;
// console.log(overpassQuery);
// return fetch(`https://overpass-api.de/api/interpreter?data=${encodeURIComponent(overpassQuery)}`)

// on document ready, click the load data button
$(document).ready(function() {
    $('#loadDataButton').click();
});

// This function fetches new data based on the bounds of a shape and returns it
async function fetchDataForShape(shape) {
    var bounds = shape.getBounds();

    let shapeType = shape.shapeType; 
    // console.log(shapeType);
    var data = [];
    if (shapeType === "rectangle") {
        console.log("rectangle");
        for (let i = 0; i < tags.length; i++) {
            try {
                // console.log(`[out:json][timeout:25];(node["${tags[i]}"](${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()}););out body;>;out skel qt;`)
                let response = await fetch(`https://overpass-api.de/api/interpreter?data=[out:json][timeout:25];
                (
                    node["${tags[i]}"](${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()});
                    way["${tags[i]}"](${bounds.getSouth()},${bounds.getWest()},${bounds.getNorth()},${bounds.getEast()});
                );
                out body;
                >;
                out skel qt;
                `);
                if (!response.ok) {
                    throw Error(`HTTP error! status: ${response.status}`);
                }
                let json = await response.json();
                data = [...data, ...json.elements];
            } catch (error) {
                console.log('Error: ', error);
            }
        }
    } 
    else if (shapeType === "circle") {
        console.log("circle");
        let center = shape.getLatLng();
        let radius = shape.getRadius();
        for (let i = 0; i < tags.length; i++) {
            try {
                let response = await fetch(`https://overpass-api.de/api/interpreter?data=[out:json][timeout:25];
                (
                    node["${tags[i]}"](around:${radius},${center.lat},${center.lng});
                    way["${tags[i]}"](around:${radius},${center.lat},${center.lng});
                );
                out body;
                >;
                out skel qt;
                `);
                if (!response.ok) {
                    throw Error(`HTTP error! status: ${response.status}`);
                }
                let json = await response.json();
                data = [...data, ...json.elements];
            } catch (error) {
                console.log('Error: ', error);
            }
        }
    } else {
        console.log("polygon");
        let points = shape.getLatLngs()[0]; // the first array is the outer ring of the polygon
        let pointString = points.map(point => `${point.lat} ${point.lng}`).join(" ");

        // Use the Overpass API polygon query syntax
        let overpassQuery = `(poly:"${pointString}")`;
        for (let i = 0; i < tags.length; i++) {
            try {
                let response = await fetch(`https://overpass-api.de/api/interpreter?data=[out:json][timeout:25];
                (
                    node["${tags[i]}"]${overpassQuery};
                    way["${tags[i]}"]${overpassQuery};
                );
                out body;
                >;
                out skel qt;
                `);
                if (!response.ok) {
                    throw Error(`HTTP error! status: ${response.status}`);
                }
                let json = await response.json();
                data = [...data, ...json.elements];
            } catch (error) {
                console.log('Error: ', error);
            }
        }

    }
    console.log("Data fetched!");
    return data;
}

map.on('draw:created', function (e) {
    var type = e.layerType,
        layer = e.layer;

    // Store the type of the shape in the layer
    layer.shapeType = type;

    // Add the drawn layer to the group
    drawnItems.addLayer(layer);
});

document.getElementById('loadDataButton').addEventListener('click', async function () {
    let response = await fetch('/geo/api/clear_data', {
        method: 'POST',
    });
    if (!response.ok) {
        throw Error(`HTTP error! status: ${response.status}`);
    }


    // Destroy existing DataTable before updating table data
    if ( $.fn.dataTable.isDataTable( '#data-table' ) ) {
        $('#data-table').DataTable().destroy();
    }

    // Clear the table body
    let tableBody = document.querySelector('#data-table tbody');
    tableBody.innerHTML = '';

    // Show the loading spinner and disable button
    document.getElementById('loader').style.display = 'block';
    document.getElementById('loadDataButton').disabled = true;
    document.getElementById('loadDataButton').style.cursor = 'wait';
    document.querySelector('#data-table thead').style.visibility = 'hidden';
    
    // Fetch data for all drawn items
    let data = [];
    let promises = [];
    drawnItems.eachLayer(function (layer) {
        // Fetch data for each shape
        promises.push(fetchDataForShape(layer));
    });
    let results = await Promise.all(promises);
    results.forEach(res => {
        data = [...data, ...res];
    });

    // Send all data to the server at once
    response = await fetch('/geo/api/process_data', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ elements: data })
    });
    if (!response.ok) {
        throw Error(`HTTP error! status: ${response.status}`);
    }

    // Load the data into the table (or whatever you want to do with it)
    await loadData();

    // Hide the loader and renable button
    document.getElementById('loader').style.display = 'none';
    document.getElementById('loadDataButton').disabled = false;
    document.getElementById('loadDataButton').style.cursor = 'default';
    document.querySelector('#data-table thead').style.visibility = 'visible';
});

// This function will generate the child row content.
function formatDetail ( node ) {
    let tagDetails = '';
    Object.entries(node.tags).forEach(([key, value]) => {
        tagDetails += `<p><b>${key}:</b> ${value}</p>`;
    });
    return `<div class="detail-container">${tagDetails}</div>`;
}

let dataTable = null;

let detailsData = [];  // Array to hold details data

async function loadData() {
    const response = await fetch('/geo/api/get_data');
    const data = await response.json();

    let tableBody = document.querySelector('#data-table tbody');
    tableBody.innerHTML = '';

    // Clear detailsData array
    detailsData = [];

    data.forEach((node, i) => {
        let row = document.createElement('tr');

        // Create data cells
        let cells = [node.tags.name, node.type];
        cells.forEach(cell => {
            let cellElement = document.createElement('td');
            cellElement.textContent = cell;
            row.appendChild(cellElement);
        });

        // Create details control cell and append it to the row
        let detailCell = document.createElement('td');
        detailCell.className = "details-control";
        row.appendChild(detailCell);

        // Store the data for the details view in the row
        let tagsList = Object.entries(node.tags).map(([key, value]) => `<b>${key}</b>: ${value}`);
        let tagsString = tagsList.join('&emsp;');
        if (node.lat !== undefined && node.lon !== undefined){
            row.dataset.details = `<b>Latitude</b>: ${node.lat}&emsp;<b>Longitude</b>: ${node.lon}&emsp;${tagsString}`;
        } else {
            row.dataset.details = tagsString;
        }
        

        // Add details data to array
        detailsData.push(row.dataset.details);

        tableBody.appendChild(row);
    });

    // Initialize DataTable
    let table = $('#data-table').DataTable({
        "columns": [
            { "data": "tags.name" },
            { "data": "type" },
            {
                "data": null,
                "className": 'details-control',
                "orderable": false,
                "defaultContent": '',
                "render": function(data, type, row, meta) {
                    // Return details data for search and order actions
                    if (type === 'filter' || type === 'sort') {
                        return detailsData[meta.row];
                    }
                    return '';
                }
            }
        ],
        "order": [[1, 'asc']]
    });

    // Add event listener for opening and closing details
    $('#data-table tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row(tr);

        if (row.child.isShown()) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        } else {
            // Open this row
            row.child(tr.data('details')).show();
            tr.addClass('shown');
        }
    });
}




function formatDetail(rowData) {
    return `<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">
        <tr>
            <td>Latitude:</td>
            <td>${rowData.lat}</td>
        </tr>
        <tr>
            <td>Longitude:</td>
            <td>${rowData.lon}</td>
        </tr>
        <tr>
            <td>Tags:</td>
            <td>${rowData.tags}</td>
        </tr>
    </table>`;
}
