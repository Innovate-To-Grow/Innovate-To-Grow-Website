// Cookies
document.getElementById("cookies").style.display = "none";
if (!navigator.cookieEnabled) {
    document.getElementById("cookies").style.display = "block";
    document.getElementById("map").style.display = "none";
    document.getElementById("loadDataButton").style.display = "none";
    document.getElementById("saveShapesButton").style.display = "none";
    document.getElementById("savedShapesSelection").style.display = "none";
    document.getElementById("data-table").style.display = "none";
    document.getElementById("data-table_wrapper").style.display = "none";
}

let select_count2 = 0; // keeps track of how many rows are selected
let tags = ["shop", "amenity", "building"]

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
$(document).ready(function () {
    $('#loadDataButton').click();
});

// This function fetches new data based on the bounds of a shape and returns it
async function fetchDataForShape(shape) {
    var bounds = shape.getBounds();

    let shapeType = shape.shapeType;
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
                out body meta;
                >;
                out skel qt;
                `);
                if (!response.ok) {
                    throw Error(`HTTP error! status: ${response.status}`);
                }
                let json = await response.json();
                let filteredJson = json.elements.filter(element => {
                    if (element.hasOwnProperty('tags')) {
                        if (element.tags.hasOwnProperty('name')) {
                            return true;
                        }
                    }
                    return false;
                });

                data = [...data, ...filteredJson];

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
                out body meta;
                >;
                out skel qt;
                `);
                if (!response.ok) {
                    throw Error(`HTTP error! status: ${response.status}`);
                }
                let json = await response.json();
                let filteredJson = json.elements.filter(element => {
                    if (element.hasOwnProperty('tags')) {
                        if (element.tags.hasOwnProperty('name')) {
                            return true;
                        }
                    }
                    return false;
                });

                data = [...data, ...filteredJson];

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
                out body meta;
                >;
                out skel qt;
                `);
                if (!response.ok) {
                    throw Error(`HTTP error! status: ${response.status}`);
                }
                let json = await response.json();
                let filteredJson = json.elements.filter(element => {
                    if (element.hasOwnProperty('tags')) {
                        if (element.tags.hasOwnProperty('name')) {
                            return true;
                        }
                    }
                    return false;
                });

                data = [...data, ...filteredJson];

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



// Saving function
function saveShapeSelection() {
    if (drawnItems.getLayers().length != 0) {
        let name = prompt("Please enter a name for this selection");
        // if name is null (which happens if Cancel is clicked) or empty, return from the function
        if (name === null || name === "") {
            if (name === "") alert("You must enter a valid name!");
            return;
        }

        let selectedShapes = {
            type: "FeatureCollection",
            features: []
        };

        drawnItems.eachLayer(function (layer) {
            let shapeType;
            if (layer instanceof L.Circle) {
                shapeType = "circle";
                selectedShapes.features.push({
                    type: "Feature",
                    geometry: {
                        type: "Point",
                        coordinates: [layer.getLatLng().lng, layer.getLatLng().lat]
                    },
                    properties: {
                        radius: layer.getRadius(),
                        shapeType: shapeType
                    }
                });
            } else if (layer instanceof L.Rectangle) {
                shapeType = "rectangle";
                let feature = layer.toGeoJSON();
                feature.properties.shapeType = shapeType;
                selectedShapes.features.push(feature);
            } else {
                // Defaulting to polygon if it's not a circle or a rectangle.
                shapeType = "polygon";
                let feature = layer.toGeoJSON();
                feature.properties.shapeType = shapeType;
                selectedShapes.features.push(feature);
            }
        });

        // Save the selection into the local storage
        let savedShapes = JSON.parse(localStorage.getItem('savedShapes')) || {};
        savedShapes[name] = selectedShapes;
        localStorage.setItem('savedShapes', JSON.stringify(savedShapes));
        updateShapeSelectionDropdown();
    } else {
        alert("You must draw a shape first!");
        return;
    }
}

// Loading function
function loadShapeSelection() {
    // Get the saved selections from the local storage
    let savedShapes = JSON.parse(localStorage.getItem('savedShapes'));
    let selectElement = document.getElementById('savedShapesSelection');
    // Get the selected name from the dropdown
    let name = document.getElementById('savedShapesSelection').value;

    if (!name || !(name in savedShapes)) {
        console.log("No saved selections found with this name!");
        return;
    }

    // Load the selected shapes
    let selectedShapes = savedShapes[name];

    // Clear the drawn items
    drawnItems.clearLayers();

    // Load the shapes into the layer group
    L.geoJSON(selectedShapes, {
        pointToLayer: function (feature, latlng) {
            if (feature.properties.shapeType === "circle") {
                let circle = L.circle(latlng, { radius: feature.properties.radius });
                circle.shapeType = feature.properties.shapeType;
                drawnItems.addLayer(circle);
            }
        },
        onEachFeature: function (feature, layer) {
            if (feature.properties.shapeType === "rectangle" || feature.properties.shapeType === "polygon") {
                layer.shapeType = feature.properties.shapeType;
                drawnItems.addLayer(layer);
            }
        }
    });
    updateShapeSelectionDropdown();
    map.fitBounds(drawnItems.getBounds());
}

updateShapeSelectionDropdown();

document.getElementById('saveShapesButton').addEventListener('click', saveShapeSelection);
document.getElementById('savedShapesSelection').addEventListener('change', loadShapeSelection);


// Update the dropdown with the names of saved shapes
function updateShapeSelectionDropdown() {
    let savedShapes = JSON.parse(localStorage.getItem('savedShapes')) || {};
    let selectElement = document.getElementById('savedShapesSelection');

    // Clear the current options
    selectElement.innerHTML = "";

    // Create a default option
    let defaultOption = document.createElement("option");
    defaultOption.text = "Load Shapes";
    defaultOption.value = "";
    selectElement.add(defaultOption);

    // Add an option for each saved shape
    for (let name in savedShapes) {
        let option = document.createElement("option");
        option.text = name;
        option.value = name;
        selectElement.add(option);
    }
}


document.getElementById('loadDataButton').addEventListener('click', async function () {
    let response = await fetch('/geo/api/clear_data', {
        method: 'POST',
    });
    if (!response.ok) {
        throw Error(`HTTP error! status: ${response.status}`);
    }


    // Destroy existing DataTable before updating table data
    if ($.fn.dataTable.isDataTable('#data-table')) {
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

let dataTable = null;
let detailsData = [];  // Array to hold details data
// Function to move the search bar on page load
function moveSearchBar() {
    let searchContainer = $("#data-dateFilterDropdown .search-bar");
    let searchBar = $("#data-table_filter");
  
    // If the search bar already exists in the search container, remove it
    if (searchContainer.children().length > 0) {
        searchContainer.empty();
    }

    // Move the search bar to the search container
    searchContainer.append(searchBar.children());
}

async function loadData() {
    const response = await fetch('/geo/api/get_data');
    const data = await response.json();

    let tableBody = document.querySelector('#data-table tbody');
    tableBody.innerHTML = '';

    // Clear detailsData array
    detailsData = [];

    data.forEach((node, i) => {
        let row = document.createElement('tr');

        // Convert timestamp to PST and format it
        let date = new Date(node.timestamp);
        let formattedDate = new Intl.DateTimeFormat('en-US', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: true,
            timeZone: 'America/Los_Angeles'
        }).format(date);

        formattedDate = formattedDate.replace(',', ''); // remove comma

        // Split the date and time parts
        let [datePart, timePart, period] = formattedDate.split(' ');

        // Split the date part into month, day, year
        let [month, day, year] = datePart.split('/');

        // Re-order the parts to 'YYYY-MM-DD'
        datePart = `${year}-${month}-${day}`;

        // Combine the parts again
        formattedDate = `${datePart} ${timePart} ${period}`;

        // Add a checkbox cell
        let checkboxCell = document.createElement('td');
        let checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'row-checkbox';
        checkboxCell.appendChild(checkbox);
        row.appendChild(checkboxCell);

        // Create data cells
        let cells = [node.tags.name, node.type, formattedDate];
        cells.forEach(cell => {
            let cellElement = document.createElement('td');
            cellElement.textContent = cell;
            row.appendChild(cellElement);
        });

        // Create details control cell and append it to the row
        let detailCell = document.createElement('td');
        // detailCell.className = "details-control";
        row.appendChild(detailCell);

        // Store the data for the details view in the row
        let tagsList = Object.entries(node.tags).map(([key, value]) => `<b>${key}</b>: ${value}`);
        let tagsString = tagsList.join('&emsp;');

        if (node.lat !== undefined && node.lon !== undefined) {
            row.dataset.details = `<b>Latitude</b>: ${node.lat}&emsp;<b>Longitude</b>: ${node.lon}&emsp;${tagsString}`;
        }

        else {
            row.dataset.details = tagsString;
        }

        // Add details data to array
        detailsData.push(row.dataset.details);

        tableBody.appendChild(row);
    });

    // Custom filtering function which will search data in column four between two values
    $.fn.dataTable.ext.search.push(
        function (settings, data, dataIndex) {
            if (settings.nTable.id !== 'data-table') {
                return true;
            }

            let min = new Date($('#data-min-date').val()).getTime();
            let max = new Date($('#data-max-date').val()).getTime();
            let date = new Date(data[3]).getTime(); // column number where date data is

            if ((isNaN(min) && isNaN(max)) ||
                (isNaN(min) && date <= max) ||
                (min <= date && isNaN(max)) ||
                (min <= date && date <= max)) {
                return true;
            }
            return false;
        }
    );

    var dropdown = document.getElementById("data-dateFilterDropdown");
    dropdown.style.display = "block";

    // Initialize DataTable
    let table = $('#data-table').DataTable({
        "columns": [
            { "data": null, "defaultContent": "<input type='checkbox' class='row-checkbox'>" }, // Checkbox column
            { "data": "tags.name" },
            { "data": "type" },
            { "data": "timestamp" },
            {
                "data": null,
                "className": 'details-control',
                "orderable": false,
                "defaultContent": '',
                "render": function (data, type, row, meta) {
                    if (type === 'filter' || type === 'sort') {
                        return detailsData[meta.row];
                    }
                    return '';
                }
            }
        ],
        "order": [[1, 'asc']],
        "columnDefs": [
            { "width": "50%", "targets": 1 },
            { "width": "1%", "targets": 4 },
            { "width": "auto", "targets": "_all" }
        ],
        "stateSave": true
    });
    moveSearchBar();
    

    // Adjust table width on window resize
    $(window).resize(function () {
        var width = $(window).width();
        var newWidth = width - 16; // 8px padding on each side
        $('#data-table').css('width', newWidth);
        table.columns.adjust().draw();
    });

    // Event listener to the two range filtering inputs to redraw on input
    $('#data-min-date, #data-max-date').change(function () {
        table.draw();
    });

    // Add event listener for opening and closing details
    $('#data-table tbody').on('click', 'td.details-control', function (e) {
        e.stopPropagation();
        var tr = $(this).closest('tr');
        var row = table.row(tr);

        if (row.child.isShown()) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
            tr.next().removeClass('child-row'); // Remove the child-row class from the next row
        } else {
            // Close any other open rows
            table.rows('.shown').nodes().to$().removeClass('shown');
            table.rows('.child-row').nodes().to$().removeClass('child-row');

            // Open this row
            row.child(tr.data('details')).show();
            tr.addClass('shown');
            tr.next().addClass('child-row'); // Add the child-row class to the next row
        }
    });
}

// create master-table
$(document).ready(function () {
    // Custom filtering function which will search data in column four between two values
    $.fn.dataTable.ext.search.push(
        function (settings, data, dataIndex) {
            if (settings.nTable.id !== 'master-table') {
                return true;
            }

            let min = new Date($('#master-min-date').val()).getTime();
            let max = new Date($('#master-max-date').val()).getTime();
            let date = new Date(data[2]).getTime(); // column number where date data is

            if ((isNaN(min) && isNaN(max)) ||
                (isNaN(min) && date <= max) ||
                (min <= date && isNaN(max)) ||
                (min <= date && date <= max)) {
                return true;
            }
            return false;
        }
    );

    var dropdown = document.getElementById("master-dateFilterDropdown");
    dropdown.style.display = "block";

    let masterTable = $('#master-table').DataTable({
        "columns": [
            { "data": "tags.name" },
            { "data": "type" },
            { "data": "timestamp" },
            {
                "data": null,
                "className": 'details-control',
                "orderable": false,
                "defaultContent": '',
                "render": function (data, type, row, meta) {
                    if (type === 'filter' || type === 'sort') {
                        return detailsData[meta.row];
                    }
                    return '';
                }
            },
            {
                "data": null,
                "visible": false,
                "render": function (data, type, row, meta) {
                    return detailsData[meta.row];
                }
            }
        ],
        "order": [[0, 'asc']],
        "stateSave": true,
        "lengthChange": true,
        "dom": 'lBftrip',
        "buttons": [
            'copyHtml5', 'csvHtml5', 'excelHtml5', 'pdfHtml5', 'print'
        ],
        "columnDefs": [
            { "width": "50%", "targets": 0 },
            { "width": "1%", "targets": 3 },
            { "width": "auto", "targets": "_all" }
        ]
    });

    let searchContainer = $("#master-dateFilterDropdown .search-bar");
    searchContainer.prepend($("#master-table_filter label"));
    searchContainer.prepend($("#master-table_filter input"));

    // Adjust masterTable width on window resize
    $(window).resize(function () {
        var width = $(window).width();
        var newWidth = width - 16; // 8px padding on each side
        $('#master-table').css('width', newWidth);
        masterTable.columns.adjust().draw();
    });

    // Event listener to the two range filtering inputs to redraw on input
    $('#master-min-date, #master-max-date').change(function () {
        masterTable.draw();
    });

    // Add event listener for opening and closing details on the master-table
    $('#master-table tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = masterTable.row(tr);

        if (row.child.isShown()) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        } else {
            // Open this row
            row.child(tr.data('details')).show();
            tr.addClass('shown');
            // add class to child in order to not select it when clicking on it
            tr.next().addClass('child-row');
        }
    });

    $('#data-table tbody').on('click', 'tr', function (e) {
        var $checkbox = $(this).find('input[type="checkbox"].row-checkbox');

        // Prevent selecting row if clicking on details-control button or child row
        if ($(e.target).hasClass('details-control') || $(e.target).closest('.child-row').length > 0) {
            return;
        }

        // Prevent the double-toggle issue
        if (!$(e.target).is($checkbox) && !$(e.target).is('.row-checkbox-label')) {
            $checkbox.prop('checked', !$checkbox.prop('checked'));
        }

        $(this).toggleClass('selected');
    });

    $('#data-table tbody').on('click', 'input[type="checkbox"].row-checkbox', function (e) {
        $(this).closest('tr').toggleClass('selected');
        e.stopPropagation();
    });


    $.ajax({
        type: "POST",
        url: "/past-projects/<uuid_string>",
        data: JSON.stringify(share_datas),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        success: function (data) {
            uuid = data["uuid_string"];
            window.open("/past-projects/" + uuid, "_blank");
        },
        failure: function (errMsg) {
            alert(errMsg);
        }
    })
});

$('#merge').click(function () {
    let table = $('#data-table').DataTable();
    let merged_array = table.rows('.selected').data().toArray();
    let rows = table.rows('.selected').nodes();
    let masterTable = $('#master-table').DataTable();
    let existingData = masterTable.data().toArray(); // Get current data from masterTable

    for (let i = 0; i < merged_array.length; i++) {
        let isDuplicate = false;
        let rowData = table.row(rows[i]).data();
        let details = $(rows[i]).data('details');
        let details_json = {};

        // Generate details_json from details string
        let details_array = details.split('<br>');
        for (let j = 0; j < details_array.length; j++) {
            let detail = details_array[j].split(':');
            if (detail.length > 1) {
                let key = detail[0].trim();
                let value = detail[1].trim();
                details_json[key] = value;
            }
        }

        rowData['details'] = details_json;

        // Check if rowData already exists in masterTable
        for (let j = 0; j < existingData.length; j++) {
            // Modify this condition based on how you define two rows as identical
            // Currently, it checks if 'tags.name', 'type', 'timestamp' and 'details' are identical
            if (existingData[j]['tags.name'] === rowData['tags.name']
                && existingData[j]['type'] === rowData['type']
                && existingData[j]['timestamp'] === rowData['timestamp']
                && JSON.stringify(existingData[j]['details']) === JSON.stringify(rowData['details'])) {
                isDuplicate = true;
                break;
            }
        }

        // If rowData is not a duplicate, add it to masterTable
        if (!isDuplicate) {
            let row = masterTable.row.add(rowData).draw().node();
            $(row).data('details', details);
        }
    }
});

