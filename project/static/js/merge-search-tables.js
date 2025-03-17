// global variables START
var alert_confirmation; // confirmation answer after a merge button is pressed
var merged_table; // the actual merged DataTable
var merged_array; // turning every kept row into a merged array
var expected_merges = 0; // how many merges are expected
var deleted = [];
var deleted_counter = 0;
var search_counter = 0; // how many search tables there are
let select_count2 = 0; // keeps track of how many rows are selected
let checker = 0; // Checking if we are at a fresh merge button press
let confirmation_tracker = 0; // To Check and make sure that js alert does not be called more than once when you hit merge button
var datas = [];  //where all the data from the google sheet is stored
var share_datas = [];
var uuid;
var unique_url = false;
// global variable END

/*
 * DATABASE INTEGRATION OVERVIEW:
 * 
 * The current implementation uses a simple JSON file (databaseMergeTable.json) for data storage.
 * To implement a proper database, consider the following structure:
 *
 * Tables:
 * 1. projects - Stores individual project data with columns matching the project properties
 *    - id (primary key)
 *    - uuid (for URL friendly identifiers)
 *    - year_semester
 *    - class
 *    - team_number
 *    - team_name
 *    - project_title
 *    - organization
 *    - industry
 *    - abstract (TEXT type for longer content)
 *    - student_names (TEXT type)
 *    - created_at
 *    - updated_at
 *
 * 2. collections - Stores collection metadata
 *    - id (primary key)
 *    - collection_uuid (for URL friendly identifiers)
 *    - title
 *    - editor_content (HTML/rich text content)
 *    - created_at
 *    - updated_at
 *    - user_id (if implementing user authentication)
 *
 * 3. collection_projects - Junction table for many-to-many relationship
 *    - collection_id (foreign key to collections.id)
 *    - project_id (foreign key to projects.id)
 *    - display_order (optional, for controlling display sequence)
 *    - added_at
 *
 * This structure would support:
 * - Projects existing independently of collections
 * - Projects belonging to multiple collections
 * - Efficient queries for both projects and collections
 * - Proper data normalization for a production environment
 */



// Prep START
$(document).ready(function () {
    // get the team_names and team_numbers from the html
    team_names = JSON.parse(document.getElementById("data").dataset.team_names);
    team_numbers = JSON.parse(document.getElementById("data").dataset.team_numbers);

    $.getJSON("https://sheets.googleapis.com/v4/spreadsheets/1KATiK1Fnlb7Vsd186mCbaGjhID-OUGN-1QHWY8hIc5U/values/Past-Projects-WEB-LIVE?alt=json&key=***REMOVED_API_KEY***", function (data) {
        var length = data.values.length;
        for (var i = 1; i < length; i++) {
            const subArray = data.values[i];
            if (subArray[1] == "EngSL") {
                subArray[0] = subArray[0].replace('-EngSL', '');
            } else if (subArray[1] == "CSE") {
                subArray[0] = subArray[0].replace('-CSE', '');
            } else if (subArray[1] == "CAP") {
                subArray[0] = subArray[0].replace('-CAP', '');
            } else if (subArray[1] == "CAP1") {
                subArray[0] = subArray[0].replace('-CAP1', '');
            } else if (subArray[1] == "CEE") {
                subArray[0] = subArray[0].replace('-CEE', '');
            }
            if (team_names.length > 0 || team_numbers.length > 0) {
                if (team_names.includes(subArray[3]) && team_numbers.includes(subArray[2])) {
                    subdata = {
                        "Year-Semester": subArray[0],
                        "Class": subArray[1],
                        "Team#": subArray[2],
                        "Team Name": subArray[3],
                        "Project Title": subArray[4],
                        "Organization": subArray[5],
                        "Industry": subArray[6],
                        "Abstract": subArray[7],
                        "Student Names": subArray[8],
                    };
                    JSON.stringify(subdata);
                    datas.push(subdata);
                }

            } else {
                subdata = {
                    "Year-Semester": subArray[0],
                    "Class": subArray[1],
                        "Team#": subArray[2],
                        "Team Name": subArray[3],
                        "Project Title": subArray[4],
                        "Organization": subArray[5],
                        "Industry": subArray[6],
                        "Abstract": subArray[7],
                        "Student Names": subArray[8],
                };
                JSON.stringify(subdata);
                datas.push(subdata);

            }
        }
    });

    document.getElementById("rowdelete").disabled = true; // set delete and keep button to not work
    document.getElementById("rowkeep").disabled = true;
    $("#rowkeep").addClass('gray'); // gray out delete and keep button
    $("#rowdelete").addClass('gray');
    $(".mergeTable").hide(); // hide mergeTable div

    if (team_names.length > 0 || team_numbers.length > 0) {
        unique_url = true;
        $(".buttonStick").hide();
        $(".tableManage").hide();
        setTimeout(function () {
            $('.addtable').click(); // add a search table at the start of loading the page
            $('.merge').click(); // add a merge table at the start of loading the page
            $('.sharing').hide(); // hide the sharing button
            $('.CopyURL').show(); // show the copy url button
            $('.loader').hide();// hide the loading bar
            $(".mergeTable").show(); // hide mergeTable div
        }, 2500);
    } else {
        setTimeout(function () {
            $('.addtable').click(); // add a search table at the start of loading the page
            $('.loader').hide(); // hide the loading bar
            $('.CopyURL').hide(); // hide the copy url button
            $(".mergeTable").show(); // hide mergeTable div
        }, 2500);
    }
});
// Prep END

// Function to display abstract and student names when clicking the details button in Search Tables
function format(d) {
    // `d` is the original data object for the row
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td>Abstract:</td>' +
        '<td>' + d["Abstract"] + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td>Student Names:</td>' +
        '<td>' + d["Student Names"] + '</td>' +
        '</tr>' +
        '</table>';
}

// Function to generate a UUID from project data
function generateProjectUuid(yearSemester, classCode, teamNumber) {
    // Create a URL-friendly identifier
    // First sanitize inputs to remove any characters that would be problematic in URLs
    const sanitizedYear = yearSemester.replace(/[^a-zA-Z0-9-]/g, '-');
    const sanitizedClass = classCode.replace(/[^a-zA-Z0-9-]/g, '-');
    const sanitizedTeam = teamNumber.toString().replace(/[^a-zA-Z0-9-]/g, '-');
    
    // Format: YYYY-MM-Season-Class-TeamNumber
    return `${sanitizedYear}-${sanitizedClass}-${sanitizedTeam}`;
}

// Add this function after generateProjectUuid
function saveProjectToDatabase(projectData) {
    // Send project data to server to be stored in JSON file
    // DATABASE INTEGRATION POINT #1:
    // Replace this AJAX call with a connection to a persistent database.
    // Implement a server endpoint that stores project data in a database table 
    // such as 'projects' with columns that match the projectData structure.
    return $.ajax({
        type: "POST",
        url: "/api/save-project",
        data: JSON.stringify(projectData),
        contentType: "application/json; charset=utf-8",
        dataType: "json"
    });
}

// Generate a unique collection ID
function generateCollectionId() {
    const timestamp = new Date().toISOString().split('T')[0].replace(/-/g, '');
    const random = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
    return `curation_${timestamp}_${random}`;
}

// Create a collection from the merged table data
function createCollectionFromMergedTable() {
    const tableData = merged_table.rows().data().toArray();
    
    // Create projects array
    const projects = tableData.map(row => {
        // Generate uuid if it doesn't exist
        const uuid = row[11] || generateProjectUuid(row[0], row[1], row[2]);
        
        return {
            uuid: uuid,
            year_semester: row[0],
            class: row[1],
            team_number: row[2],
            team_name: row[3],
            project_title: row[4],
            organization: row[5],
            industry: row[6],
            abstract: row[8],
            student_names: row[9]
        };
    });
    
    // DATABASE INTEGRATION POINT #3:
    // In a database implementation:
    // 1. Create collection record first to get a database-generated ID
    // 2. Then create project records or link to existing ones
    // 3. Update relationships in the junction table
    // This would replace the all-in-one JSON structure below
    return {
        _id: generateCollectionId(),
        title: "Curated Projects - " + new Date().toLocaleDateString(),
        projects: projects,
        editorContent: "<p>Projects curated on " + new Date().toLocaleDateString() + "</p>",
        createdAt: new Date().toISOString(),
        lastUpdated: new Date().toISOString()
    };
}

// Save collection to database
function saveCollectionToDatabase(collection) {
    // DATABASE INTEGRATION POINT #2:
    // Replace with database storage for collections.
    // Implement a proper database schema with tables for:
    // 1. collections (with _id, title, editorContent, timestamps)
    // 2. projects (with project details)
    // 3. collection_projects (junction table for many-to-many relationship)
    // This would allow projects to belong to multiple collections
    return $.ajax({
        type: "POST",
        url: "/api/save-collection",
        data: JSON.stringify(collection),
        contentType: "application/json; charset=utf-8",
        dataType: "json"
    });
}

//edited****************************************************************
// Function to display all fields with edit functionality in the Merged Table
function mergeformat(d) {
    const isUuidPage = window.location.pathname.match(/\/project\/[^\/]+$/i);
    
    // Generate a project UUID if it's not already in the data
    const projectUuid = d[11] || generateProjectUuid(d[0], d[1], d[2]);
    
    // Modify to show URL with collection path parameter
    // We'll use a placeholder here that will be replaced when collection is saved
    const projectUrl = `/project/${projectUuid}`;
    
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td style="vertical-align: top;">Abstract:</td>' +
        '<td class="abstract-content" contenteditable="false" style="line-height: 1.5;">' + d[8] + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td style="vertical-align: top;">Student Names:</td>' +
        '<td class="student-names-content" contenteditable="false" style="line-height: 1.5;">' + d[9] + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td style="vertical-align: middle;">Project URL:</td>' +
        '<td style="display: flex; justify-content: space-between; align-items: center;">' +
            '<span class="project-url" style="flex: 1; padding-right: 10px;">' + projectUrl + '</span>' +
            '<button class="copy-url-btn" style="background-color: #162D4F; color: #dbaa00; border: none; padding: 5px 10px; cursor: pointer; margin: 5px 0;">' +
                '<i class="fa fa-copy"></i> Copy URL' +
            '</button>' +
        '</td>' +
        '</tr>' +
        (isUuidPage ? '' : 
        '<tr>' +
        '<td colspan="2" style="text-align: center;">' +
        '<button class="btn-edit-details" style="background-color: #162D4F; color: #dbaa00; border: none; padding: 5px 10px; cursor: pointer; margin-top: 10px;">Edit Details</button>' +
        '</td>' +
        '</tr>') +
        '</table>';
}

//edited****************************************************************
// Update the edit handler
$(document).on('click', '.btn-edit-details', function() {
    var $button = $(this);
    var $shareButton = $button.siblings('.btn-share-url');
    var $table = $button.closest('table');
    var $editableFields = $table.find('.abstract-content, .student-names-content');  // Only abstract and student names are editable
    
    if ($button.text() === 'Edit Details') {
        // Enable editing mode
        $editableFields.attr('contenteditable', 'true');
        
        // Apply common styles with vertical centering
        $editableFields.css({
            //'border': '1px solid black',
            'border-radius': '4px',
            'background-color': 'white',
            'min-height': '20px',
            'padding': '5px',
            'margin-bottom': '10px'
        });
        
        // Special styling for abstract (more space)
        $table.find('.abstract-content').css({
            'border-bottom': '1px solid #b6b6b6',
            'padding-bottom': '10px',
            'margin-bottom': '15px'
        });
        
        // Update parent td styles for proper layout
        $editableFields.parent('td').css({
            'display': 'block',
            'min-height': '40px'
        });
        
        $button.text('Discard Edit');
        $shareButton.text('Save Edit');
        
        // Store original content for potential discard
        $editableFields.each(function() {
            $(this).data('original-content', $(this).text());
        });
    } else {
        // Disable editing and revert changes
        $editableFields.attr('contenteditable', 'false');
        $editableFields.css({
            'border': 'none',
            'background-color': 'transparent',
            'padding': '0',
            'margin': '0'
        });
        
        // Reset table cell styles
        $editableFields.parent('td').css({
            'display': 'table-cell'
        });
        
        // Restore original padding and border for abstract field
        $table.find('.abstract-content').css({
            'padding-bottom': '10px',
            'border-bottom': '1px solid #b6b6b6',
            'margin-bottom': '10px'
        });
        
        $button.text('Edit Details');
        $shareButton.text('Get Shareable URL');
        
        // Restore original content
        $editableFields.each(function() {
            $(this).text($(this).data('original-content'));
        });
    }
});

//edited****************************************************************
// Current placeholder that prevents share URL functionality when in edit mode
$(document).on('click', '.btn-share-url', function(e) {
    if ($(this).text() === 'Save Edit') {
        // TODO: Implement save functionality here
        // 1. Get the edited content from abstract and student names fields
        // 2. Validate the content
        // 3. Send updates to backend/database
        // 4. Handle success/failure responses
        // 5. Update the display accordingly
        // 6. Reset button states
        e.preventDefault();
        return false;
    }
});

//edited****************************************************************
// Function to initialize share buttons behavior when on a shared URL page
function initializeShareButtons() {
    if (window.location.pathname.includes('/past-projects/')) {
        $('.btn-share-url').each(function() {
            var $button = $(this);
            var currentUrl = window.location.href;
            
            $button
                .text('Copy URL')
                .off('click')
                .on('click', function() {
                    navigator.clipboard.writeText(currentUrl);
                    $(this).text('Copied!');
                    setTimeout(function() {
                        $(this).text('Copy URL');
                    }.bind(this), 2000);
                });
        });
    }
}

//edited****************************************************************
$(document).on('click', '.copy-url-btn', function(e) {
    e.stopPropagation();
    const $btn = $(this);
    const projectUrl = $(this).siblings('.project-url').text();
    const url = window.location.origin + projectUrl;
    
    // Get the row data for this project
    const $row = $(this).closest('tr').parent().closest('tr').prev();
    const data = merged_table.row($row).data();
    
    // Create project object with UUID
    const projectUuid = data[11] || generateProjectUuid(data[0], data[1], data[2]);
    const projectData = {
        uuid: projectUuid,
        year_semester: data[0],
        class: data[1],
        team_number: data[2],
        team_name: data[3],
        project_title: data[4],
        organization: data[5],
        industry: data[6],
        abstract: data[8],
        student_names: data[9]
    };
    
    // First, check if we already have a collection saved
    $.ajax({
        type: "GET",
        url: "/api/get-latest-collection",
        dataType: "json",
        success: function(response) {
            // DATABASE INTEGRATION POINT #4:
            // Replace file-based lookup with a database query:
            // SELECT * FROM collections ORDER BY createdAt DESC LIMIT 1
            // This would retrieve the most recent collection from the database
            if (response && response.collection) {
                // Collection exists, add project to it if not already there
                const collectionId = response.collection._id;
                
                // Add this project to the collection if not already there
                $.ajax({
                    type: "POST",
                    url: `/api/add-project-to-collection/${collectionId}`,
                    // DATABASE INTEGRATION POINT #5:
                    // Replace with an INSERT or UPDATE to the collection_projects table
                    // INSERT INTO collection_projects (collection_id, project_id) VALUES (collectionId, projectId)
                    // ON DUPLICATE KEY UPDATE last_updated = NOW()
                    data: JSON.stringify(projectData),
                    contentType: "application/json; charset=utf-8",
                    dataType: "json",
                    success: function() {
                        // Copy URL with collection parameter
                        const fullUrl = window.location.origin + `/project/${projectUuid}?collection=${collectionId}`;
                        navigator.clipboard.writeText(fullUrl);
                        $btn.text('Copied!');
                        setTimeout(() => {
                            $btn.html('<i class="fa fa-copy"></i> Copy URL');
                        }, 2000);
                    }
                });
            }
        }
    });
});

// Merge Table specific functions START
$(document).ready(function () {


    // Set merged_table as a DataTable. For each specific field refer to https://datatables.net/
    merged_table = $('.display').DataTable({
        "dom": 'lBfrtip',
        "language": {
            "emptyTable": "No entries have been saved yet."
        },
        "buttons": [
            'csv', 'excel', 'pdf',
            {
                "text": 'Save & Share Collection',
                "className": 'sharing',
                "action": function () {
                    $('#share').click();
                    $('#share').remove();
                    $('.sharing').text('Saving...');
                }
            },
            {
                "text": 'Copy URL',
                "className": 'CopyURL',
                "action": function () {
                    navigator.clipboard.writeText(window.location.href);
                    $('.CopyURL').text('Copied!');
                    setTimeout(function () {
                        $('.CopyURL').text('Copy URL');
                    }, 2000);
                }
            },
            {
                // Merged table show details button
                "text": 'Show Details',
                "className": 'details-toggle-btn',
                "action": function () {
                    var $button = $('.details-toggle-btn');
                    var isShowing = $button.text() === 'Hide Details';
                    
                    $('#example').find('td.details-control-merge').each(function () {
                        var tr = $(this).closest('tr');
                        var row = merged_table.row(tr);
                        
                        if (isShowing) {
                            // Hide all details
                            if (row.child.isShown()) {
                                row.child.hide();
                                tr.removeClass('shown');
                                tr.css('color', 'Black');
                                tr.css('font-weight', 'normal');
                            }
                        } else {
                            // Show all details
                            if (!row.child.isShown()) {
                                row.child(mergeformat(row.data())).show();
                                tr.addClass('shown');
                                tr.css('color', '#162D4F');
                                tr.css('font-weight', 'bold');
                            }
                        }
                    });
                    
                    // Toggle button text
                    $button.text(isShowing ? 'Show Details' : 'Hide Details');
                }
            }
        ],
        "pageLength": 5,
        "lengthMenu": [[5, 10, 25, 100], [5, 10, 25, 100]],
        "search": {
            "search": document.location.search.replace(/^.*?\=/, '')
        },
        "aoColumns": [
            {}, {}, {}, {}, {}, {}, {},
            {
                "className": 'details-control-merge',
                "orderable": false,
                "mDataProp": "null",
                "defaultContent": ''
            },
            {
                "bVisible": false // Abstract
            },
            {
                "bVisible": false // Student Names
            },
            {
                "data": null,
                "className": "dt-center editor-delete",
                "defaultContent": '<i class="fa fa-trash"/>',
                "orderable": false
            },
            {
                "bVisible": false, // UUID column
                "data": null
            }
        ],
        order: [
            [1, 'asc']
        ],
        fixedHeader: {
            header: true,
            footer: true
        }
    });

    // Add this line at the end of the document ready function
    initializeShareButtons();

    // Detail button function, opens rows and closes them
    $('#example').on('click', 'td.details-control-merge', function () {
        var tr = $(this).closest('tr');
        var td = $(this).closest('td');
        var row = merged_table.row(tr);
        if (row.child.isShown()) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
            tr.css('color', 'Black');
            tr.css('font-weight', 'normal');
        } else {
            // Open this row
            row.child(mergeformat(row.data())).show();
            tr.addClass('shown');
            // Change color of text to tell user that the row is associated with the abstract and student name
            tr.css('color', '#162D4F');
            tr.css('font-weight', 'bold');
        }
    });

});
// Merge Table specific functions END
// Function to maintain checkbox selection state across table pages
function updateDataTableSelectAllCtrl(table) {
    var $table = table.table().node();
    var $chkbox_all = $('tbody input[type="checkbox"]', $table);
    var $chkbox_checked = $('tbody input[type="checkbox"]:checked', $table);
    var chkbox_select_all = $('thead input[name="select_all"]', $table).get(0);

    // If none of the checkboxes are checked
    if ($chkbox_checked.length === 0) {
        chkbox_select_all.checked = false;
        if ('indeterminate' in chkbox_select_all) {
            chkbox_select_all.indeterminate = false;
        }

        // If all of the checkboxes are checked
    } else if ($chkbox_checked.length === $chkbox_all.length) {
        chkbox_select_all.checked = true;
        if ('indeterminate' in chkbox_select_all) {
            chkbox_select_all.indeterminate = false;
        }

        // If some of the checkboxes are checked
    } else {
        chkbox_select_all.checked = true;
        if ('indeterminate' in chkbox_select_all) {
            chkbox_select_all.indeterminate = true;
        }
    }
}
// Handler for adding new search tables
$(document).on('click', '.addtable', function () { // adds a new search table and appends it to the .tableManage html
    search_counter++
    var rows_selected = [];
    var html =
        '<table class="display" id="example' + search_counter + '" style="width:100%">' +
        '<thead>' +
        '<tr>' +
        '<th><input name="select_all" value="' + search_counter + '" type="checkbox"></th>' +
        '<th>Year-Semester</th>' +
        '<th>Class</th>' +
        '<th>Team#</th>' +
        '<th>Team Name</th>' +
        '<th>Project Title</th>' +
        '<th>Organization</th>' +
        '<th>Industry</th>' +
        '<th>Details</th>' +
        '<th style="display:none;"></th>' +
        '<th style="display:none;"></th>' +
        '</tr>' +
        '</thead>' +
        '</table>';
    $(".tableManage").append(html);

    // Set search_table as a DataTable. For each specific field refer to https://datatables.net/
    var search_table = $('#example' + search_counter).DataTable({
        "dom": 'lBfrtip',
        select: {
            info: false,
            style: 'multi'

        },
        "buttons": [
            {
                "text": 'Select All Entries',
                "action": function () {
                    select_count2 -= search_table.rows('.selected').count();
                    search_table.rows().select();
                    search_table.$('tr').find('input[type="checkbox"]').prop('checked', true);
                    // $('th').find('input[type="checkbox"]').prop('checked', true);
                    select_count2 += search_table.rows('.selected').count();
                    search_table.page('next').draw(false);
                    search_table.page('previous').draw(false);
                    if (select_count2 > 0) {
                        document.getElementById("rowdelete").disabled = false;
                        document.getElementById("rowkeep").disabled = false;
                        $("#rowkeep").removeClass('gray');
                        $("#rowdelete").removeClass('gray');
                    } else {
                        document.getElementById("rowdelete").disabled = true;
                        document.getElementById("rowkeep").disabled = true;
                        $("#rowkeep").addClass('gray');
                        $("#rowdelete").addClass('gray');
                    }
                }
            },
            {
                "text": 'Deselect',
                "action": function () {
                    select_count2 -= search_table.rows('.selected').count();
                    search_table.rows().deselect();
                    search_table.$('tr').find('input[type="checkbox"]').prop('checked', false);
                    search_table.page('next').draw(false);
                    search_table.page('previous').draw(false);
                    if (select_count2 > 0) {
                        document.getElementById("rowdelete").disabled = false;
                        document.getElementById("rowkeep").disabled = false;
                        $("#rowkeep").removeClass('gray');
                        $("#rowdelete").removeClass('gray');
                    } else {
                        document.getElementById("rowdelete").disabled = true;
                        document.getElementById("rowkeep").disabled = true;
                        $("#rowkeep").addClass('gray');
                        $("#rowdelete").addClass('gray');
                    }
                }
            },
            {
                //search table show all details button
                "text": "Show all details",
                "action": function () {
                    $('#example' + search_counter).find('td.details-control').each(function () {
                        var tr = $(this).closest('tr');
                        var td = $(this).closest('td');
                        //$(this).parent().find('input[type="checkbox"]').trigger('click'); this line causes show details button to select all rows
                        var row = search_table.row(tr);
                        if (row.child.isShown()) {
                            row.child.hide();
                            tr.removeClass('shown');
                            tr.css('color', 'Black');
                            tr.css('font-weight', 'normal');
                        } else {
                            row.child(format(row.data())).show();
                            tr.addClass('shown');
                            tr.css('color', '#162D4F');
                            tr.css('font-weight', 'bold');
                        }
                    });
                } 
            }
        ],
        "pageLength": 5,
        "lengthMenu": [[5, 10, 25, 100], [5, 10, 25, 100]],
        "search": {
            "search": document.location.search.replace(/^.*?\=/, '')
        },
        data: datas,
        columns: [
            {
                'targets': 0,
                'searchable': false,
                'orderable': false,
                'width': '1%',
                'className': 'dt-body-center cum',
                'render': function (data, type, full, meta) {
                    return '<input type="checkbox">';
                }
            },
            { "data": "Year-Semester" },
            { "data": "Class" },
            { "data": "Team#" },
            { "data": "Team Name" },
            { "data": "Project Title" },
            { "data": "Organization" },
            { "data": "Industry" },
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "defaultContent": ''
            },
            {
                // true shows abstract but formatting is super ugly; false does not show abstract by default
                "data": "Abstract",
                "bVisible": false
            },
            {
                "data": "Student Names",
                "bVisible": false
            }
        ],
        order: [
            [1, 'desc']
        ],
        orderFixed: {
            post: [[2, 'asc']]
        },
        fixedHeader: {
            header: true,
            footer: true
        }
    });
    // Handle click on checkbox
    $('#example' + search_counter + ' tbody').on('click', 'input[type="checkbox"]', function (e) {
        var $row = $(this).closest('tr');

        // Get row data
        var data = search_table.row($row).data();

        // Get row ID
        var rowId = data[0];

        // Determine whether row ID is in the list of selected row IDs 
        var index = $.inArray(rowId, rows_selected);

        // If checkbox is checked and row ID is not in list of selected row IDs
        if (this.checked && index === -1) {
            rows_selected.push(rowId);

            // Otherwise, if checkbox is not checked and row ID is in list of selected row IDs
        } else if (!this.checked && index !== -1) {
            rows_selected.splice(index, 1);
        }

        if (this.checked) {
            $row.addClass('selected');
            select_count2++;
        } else {
            $row.removeClass('selected');
            select_count2--;
        }
        if (select_count2 > 0) {
            document.getElementById("rowdelete").disabled = false;
            document.getElementById("rowkeep").disabled = false;
            $("#rowkeep").removeClass('gray');
            $("#rowdelete").removeClass('gray');
        } else {
            document.getElementById("rowdelete").disabled = true;
            document.getElementById("rowkeep").disabled = true;
            $("#rowkeep").addClass('gray');
            $("#rowdelete").addClass('gray');
        }

        // Update state of "Select all" control
        updateDataTableSelectAllCtrl(search_table);

        // Prevent click event from propagating to parent
        e.stopPropagation();
    });

    // Handle click on table cells with checkboxes
    $('#example' + search_counter).on('click', 'tbody td, thead th:first-child', function (e) {
        $(this).parent().find('input[type="checkbox"]').trigger('click');
        e.stopPropagation();
    });

    // Handle click on "Select all" control
    $('thead input[name="select_all"]', search_table.table().container()).on('click', function (e) {
        if (this.checked) {
            $('#example' + this.value + ' tbody input[type="checkbox"]:not(:checked)').trigger('click');
        } else {
            $('#example' + this.value + ' tbody input[type="checkbox"]:checked').trigger('click');
        }

        // Prevent click event from propagating to parent
        e.stopPropagation();
    });

    // Handle table draw event
    search_table.on('draw', function () {
        // Update state of "Select all" control
        updateDataTableSelectAllCtrl(search_table);
    });

    // Delete row function
    $('#rowdelete').click(function () {
        search_table.rows('.selected').remove().draw(false);
        select_count2 = 0;
        document.getElementById("rowdelete").disabled = true;
        document.getElementById("rowkeep").disabled = true;
        $("#rowkeep").addClass('gray');
        $("#rowdelete").addClass('gray');
    });

    // Keep row function
    $('#rowkeep').click(function () {
        if (search_table.$('tr').hasClass('keep') != true) {
            search_table.$('tr').toggleClass('selected');
            search_table.rows('.selected').remove().draw();
            search_table.$('tr').toggleClass('keep');
            search_table.rows().deselect();
            search_table.$('tr').find('input[type="checkbox"]').prop('checked', false);
            $('.cum').find('input[type="checkbox"]').prop('checked', false);
            select_count2 = 0;
        }
        document.getElementById("rowdelete").disabled = true;
        document.getElementById("rowkeep").disabled = true;
        $("#rowkeep").addClass('gray');
        $("#rowdelete").addClass('gray');
    });

    // Handler for merging selected items into the merged table
    $('#merge').click(function () {
        var first_merge = false;

        if (unique_url == true) {
            $(".mergeTable").show();
            merged_array = search_table.rows({ filter: 'applied' }).data().toArray();
            for (let i = 0; i < merged_array.length; i++) {
                var row = merged_table.row($(this).closest('tr'));
                merged_table.row.add([
                    merged_array[i]["Year-Semester"],
                    merged_array[i]["Class"],
                    merged_array[i]["Team#"],
                    merged_array[i]["Team Name"],
                    merged_array[i]["Project Title"],
                    merged_array[i]["Organization"],
                    merged_array[i]["Industry"],
                    merged_array[i]["null"],
                    merged_array[i]["Abstract"],
                    merged_array[i]["Student Names"],
                    generateProjectUuid(merged_array[i]["Year-Semester"], merged_array[i]["Class"], merged_array[i]["Team#"])
                ]).draw();
            }
            merged_table.$('tr').toggleClass('keep');
            for (let i = search_counter; i > 0; i--) {
                $('#example' + i).DataTable().destroy();
                $('#example' + i).remove();
            }
        } else {
            if (confirmation_tracker == 0) { // if its a fresh start, makes sure to ask for confirmation only once per press
                if (confirm("Are you sure you want to merge all of your search tables? \n(this can not be undone!)")) {
                    alert_confirmation = true;
                    $(".mergeTable").show();

                    if (deleted.length == 0) {
                        deleted[0] = new Set();
                        first_merge = true;
                    }

                    function count_search_tables() {
                        var count = $('[id^="example"]').filter(function () {
                            return /example\d_wrapper$/.test(this.id);
                        }).length;
                        return count;
                    }

                    if (first_merge == true) {
                        expected_merges = count_search_tables() - 1;
                    }
                    else {
                        expected_merges = deleted.length + count_search_tables() - 1;
                    }

                    merged_array = search_table.rows({ filter: 'applied' }).data().toArray(); // turn kept rows into an array

                    merged_array = merged_array.filter(function (element) {
                        var is_deleted = false;
                        deleted[0].forEach(function (del_element) {
                            if (element["Year-Semester"] == del_element["Year-Semester"] &&
                                element["Class"] == del_element["Class"] &&
                                element["Team#"] == del_element["Team#"] &&
                                element["Team Name"] == del_element["Team Name"] &&
                                element["Project Title"] == del_element["Project Title"] &&
                                element["Organization"] == del_element["Organization"] &&
                                element["Industry"] == del_element["Industry"] &&
                                element["Abstract"] == del_element["Abstract"] &&
                                element["Student Names"] == del_element["Student Names"]) {
                                is_deleted = true;
                            }
                        });
                        return !is_deleted;
                    });

                    $('#example').DataTable().clear().draw(); // delete old table
                    for (let i = 0; i < merged_array.length; i++) { // set 2D array as necessary
                        var row = merged_table.row($(this).closest('tr'));
                        merged_table.row.add([
                            merged_array[i]["Year-Semester"],
                            merged_array[i]["Class"],
                            merged_array[i]["Team#"],
                            merged_array[i]["Team Name"],
                            merged_array[i]["Project Title"],
                            merged_array[i]["Organization"],
                            merged_array[i]["Industry"],
                            merged_array[i]["null"],
                            merged_array[i]["Abstract"],
                            merged_array[i]["Student Names"],
                            deleted_counter,
                            generateProjectUuid(merged_array[i]["Year-Semester"], merged_array[i]["Class"], merged_array[i]["Team#"])
                        ]).draw();
                    }
                    merged_table.$('tr').toggleClass('keep');
                    for (let i = search_counter; i > 0; i--) { // delete search tables after merge
                        $('#example' + i).DataTable().destroy();
                        $('#example' + i).remove();
                    }
                }
                else {
                    alert_confirmation = false;
                }
            }
            else if (confirmation_tracker != 0 && alert_confirmation == true) { // allows the merge to continue if confirmation is true
                $(".mergeTable").show();

                deleted_counter++;
                if (deleted.length == deleted_counter) {
                    deleted[deleted_counter] = new Set();
                }

                merged_array = search_table.rows({ filter: 'applied' }).data().toArray();

                merged_array = merged_array.filter(function (element) {
                    var is_deleted = false;
                    deleted[deleted_counter].forEach(function (del_element) {
                        if (element["Year-Semester"] == del_element["Year-Semester"] &&
                            element["Class"] == del_element["Class"] &&
                            element["Team#"] == del_element["Team#"] &&
                            element["Team Name"] == del_element["Team Name"] &&
                            element["Project Title"] == del_element["Project Title"] &&
                            element["Organization"] == del_element["Organization"] &&
                            element["Industry"] == del_element["Industry"] &&
                            element["Abstract"] == del_element["Abstract"] &&
                            element["Student Names"] == del_element["Student Names"]) {
                            is_deleted = true;
                        }
                    });
                    return !is_deleted;
                });

                for (let i = 0; i < merged_array.length; i++) {
                    var row = merged_table.row($(this).closest('tr'));
                    var data = merged_table.rows().data().toArray();
                    var found = data.find(function (element) {
                        return element[0] == merged_array[i]["Year-Semester"] &&
                            element[1] == merged_array[i]["Class"] &&
                            element[2] == merged_array[i]["Team#"] &&
                            element[3] == merged_array[i]["Team Name"] &&
                            element[4] == merged_array[i]["Project Title"] &&
                            element[5] == merged_array[i]["Organization"] &&
                            element[6] == merged_array[i]["Industry"] &&
                            element[7] == merged_array[i]["null"] &&
                            element[8] == merged_array[i]["Abstract"] &&
                            element[9] == merged_array[i]["Student Names"];
                    });

                    if (found) {
                        continue;
                    }

                    merged_table.row.add([
                        merged_array[i]["Year-Semester"],
                        merged_array[i]["Class"],
                        merged_array[i]["Team#"],
                        merged_array[i]["Team Name"],
                        merged_array[i]["Project Title"],
                        merged_array[i]["Organization"],
                        merged_array[i]["Industry"],
                        merged_array[i]["null"],
                        merged_array[i]["Abstract"],
                        merged_array[i]["Student Names"],
                        deleted_counter,
                        generateProjectUuid(merged_array[i]["Year-Semester"], merged_array[i]["Class"], merged_array[i]["Team#"])
                    ]).draw();
                }
                merged_table.$('tr').toggleClass('keep');
                for (let i = search_counter; i > 0; i--) {
                    $('#example' + i).DataTable().destroy();
                    $('#example' + i).remove();
                }
            }
            confirmation_tracker++;

            if (deleted_counter == expected_merges) {
                deleted_counter = 0;
            }
        }

        $('#example').on('click', 'td.editor-delete', function () {
            // delete row in merged_table and search_table and update merged_array when trash can is clicked
            var data = merged_table.row($(this).parents('tr')).data();
            if (deleted.length > 0) {
                deleted[data[10]].add({
                    "Year-Semester": data[0],
                    "Class": data[1],
                    "Team#": data[2],
                    "Team Name": data[3],
                    "Project Title": data[4],
                    "Organization": data[5],
                    "Industry": data[6],
                    "Abstract": data[8],
                    "Student Names": data[9]
                });
            }

            merged_table.row($(this).parents('tr')).remove().draw();
        });
    });

    // Detail button function, opens rows and closes them
    $('#example' + search_counter).on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var td = $(this).closest('td');
        $(this).parent().find('input[type="checkbox"]').trigger('click');
        var row = search_table.row(tr);
        if (row.child.isShown()) {
            row.child.hide();
            tr.removeClass('shown');
            tr.css('color', 'Black');
            tr.css('font-weight', 'normal');
        } else {
            // Open this row
            row.child(format(row.data())).show();
            tr.addClass('shown');
            //change color of text to tell user that the row is assosiated to the abstract and student name
            tr.css('color', '#162D4F');
            tr.css('font-weight', 'bold');
        }
    });

    // spacer between each search table
    var line = '<p id="hr' + search_counter + '" style="margin-top:75px;"></p>';
    $(".tableManage").append(line);

    checker++;
});
// All functions under the search table scope (.addtable) END

// Disable merge button if there are no search tables
$(document).ready(function () {
    function disable_merge() {
        if (!$('[id^="example"]').filter(function () {
            return /example\d_wrapper$/.test(this.id);
        }).length) {
            $('.merge').prop('disabled', true);
            $('.merge').css('background-color', '#5B5B5B');
        }
        else {
            $('.merge').prop('disabled', false);
            $('.merge').css('background-color', '#162D4F');
        }
    }
    setInterval(disable_merge, 100);
});

// to reset the confirmation tracker back to 0; in order to ask for merge confirmation again (must be out .addTable scope)
$(document).on('click', '.merge', function () {
    if (checker == search_counter) {
        confirmation_tracker = 0;
    }
});

// Delete table function (Out of .addTable scope in order to delete any search table)
$(document).ready(function () {
    var delete_button = document.getElementById("tabledelete");
    var delete_status = delete_button.value;

    delete_button.addEventListener('click', () => {
        if (delete_status == "false") {
            delete_status = "true";
        } else {
            delete_status = "false";
        }
        $('.tableManage').on('click', 'table.display', function () {
            if (delete_status == "true") {
                var table = $(this).closest('table');
                table.DataTable().clear().destroy();
                table.remove();
                document.getElementById("rowdelete").disabled = true;
                document.getElementById("rowkeep").disabled = true;
                $("#rowkeep").addClass('gray');
                $("#rowdelete").addClass('gray');
                select_count2 = 0;
                document.getElementById("tabledelete").checked = false;
                delete_status = "false";
            }
        })
    });


    $('#share').click(function () {
        $(this).hide();
        
        // Create a collection from the merged table
        const collection = createCollectionFromMergedTable();
        
        // Save the collection to the database
        $.ajax({
            type: "POST",
            url: "/api/save-collection",
            data: JSON.stringify(collection),
            contentType: "application/json; charset=utf-8",
            dataType: "json",
            success: function (data) {
                // Open the collection page
                window.open(`/collection/${collection._id}`, "_blank");
                
                // Update collection ID for all URLs
                $('.project-url').each(function() {
                    const projectId = $(this).text().split('/').pop();
                    $(this).text(`/project/${projectId}?collection=${collection._id}`);
                });
                
                // Update UI with more accurate text
                $('.sharing').text('Collection Saved!');
                setTimeout(function() {
                    $('.sharing').text('Save & Share Collection');
                }, 2000);
            },
            failure: function (errMsg) {
                $('.sharing').text('Error Saving Collection');
                setTimeout(function() {
                    $('.sharing').text('Save & Share Collection');
                }, 2000);
                alert(errMsg);
            }
        });
    });
});
