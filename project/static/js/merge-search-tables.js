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
var currentCollectionId = null; // Tracks the current collection ID
var currentCollectionTitle = null; // Tracks the current collection title
var titleChanged = false; // Flag to track if title has been edited
var currentCreatedAt = null; // Tracks the original creation timestamp
// Add this variable to track editor content
let currentEditorContent = "";
// global variable END

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
            $('.loader').hide();// hide the loading bar
            $(".mergeTable").show(); // hide mergeTable div
        }, 2500);
    } else {
        setTimeout(function () {
            $('.addtable').click(); // add a search table at the start of loading the page
            $('.loader').hide(); // hide the loading bar
            $(".mergeTable").show(); // hide mergeTable div
        }, 2500);
    }

    // Add custom styles for title editing
    $('head').append(`
        <style>
            #curation-title-container {
                margin-bottom: 20px;
                padding: 15px;
                border-radius: 5px;
                background-color: #f9f9f9;
                border: 1px solid #e0e0e0;
            }
            #curation-title:focus {
                outline: none;
                border-color: #162D4F;
                box-shadow: 0 0 0 2px rgba(22, 45, 79, 0.2);
            }
            #save-title-btn:hover {
                background-color: #0e1d33 !important;
            }
        </style>
    `);

    // Add this near the top of your document.ready function to log collection ID status on page load
    // Add this after your other document.ready setup code
    
    // Check if URL contains collection parameter and extract it
    const urlParams = new URLSearchParams(window.location.search);
    const collectionParam = urlParams.get('collection');
    
    if (collectionParam) {
        console.log("Collection ID from URL:", collectionParam);
        // Set current collection ID from URL parameter
        currentCollectionId = collectionParam;
        
        // Fetch initial collection data on page load
        $.ajax({
            type: "GET",
            url: `/api/get-collection/${currentCollectionId}`,
            dataType: "json"
        })
        .done(function(data) {
            console.log("Loaded collection data on page init:", data);
            if (data && data.editorContent !== undefined) {
                currentEditorContent = data.editorContent;
                console.log("Initialized editor content:", currentEditorContent);
            }
            if (data && data.title) {
                currentCollectionTitle = data.title;
            }
            if (data && data.createdAt) {
                currentCreatedAt = data.createdAt;
            }
        })
        .fail(function(error) {
            console.error("Failed to load initial collection:", error);
        });
    } else {
        console.log("No collection ID in URL, will create new collection when saving.");
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

// Function to generate a UUID from project data by hashing collection ID and project title
function generateProjectUuid(yearSemester, classCode, teamNumber, projectTitle) {
    // Get current collection ID if available, otherwise use a timestamp
    const collectionContext = currentCollectionId || ('temp_' + new Date().getTime());
    
    // Combine project title with collection context to create a unique string
    const baseString = `${collectionContext}-${projectTitle || yearSemester+classCode+teamNumber}`;
    
    // Create a simple hash from the string
    // This implements a basic hash function that produces a hex string
    let hash = 0;
    for (let i = 0; i < baseString.length; i++) {
        const char = baseString.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32bit integer
    }
    
    // Convert to hex and ensure positive value
    const hexHash = Math.abs(hash).toString(16);
    
    // Add a prefix to make it clear this is a project ID
    return `proj-${hexHash}`;
}

// Add this function after generateProjectUuid
function saveProjectToDatabase(projectData) {
    return $.ajax({
        type: "POST",
        url: "/api/save-project",  // This now routes to merge_blueprint
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

// Update the createCollectionFromMergedTable function to include editor content

function createCollectionFromMergedTable() {
    const tableData = merged_table.rows().data().toArray();
    
    // Create projects array
    const projects = tableData.map(row => {
        // Generate uuid if it doesn't exist
        const uuid = row[11] || generateProjectUuid(row[0], row[1], row[2], row[4]); // row[4] contains the project title
        
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
    
    // Use the existing collection ID if available, otherwise generate a new one
    const collectionId = currentCollectionId || generateCollectionId();
    
    // Get the title from the input field if available, otherwise use default
    let title = $('#curation-title').length ? 
                $('#curation-title').val().trim() : 
                (currentCollectionTitle || "Curated Projects - " + new Date().toLocaleDateString());
    
    // If title is empty, use default
    if (!title) {
        title = "Curated Projects - " + new Date().toLocaleDateString();
    }
    
    // Save the current title
    currentCollectionTitle = title;
    
    // Always include createdAt field, but use existing time for updates
    const now = new Date().toISOString();
    
    // Modified this section to handle editorContent correctly
    // Don't try to get the content from the editor if we're just creating the base collection
    // Only use the editor's content when explicitly saving edits
    let editorContent;
    
    // Check if this is being called from saveProjectEdits
    const calledFromSave = new Error().stack.includes('saveProjectEdits');
    
    if (calledFromSave && $('#project-editor').length) {
        // If called from saveProjectEdits and editor exists, get current content
        editorContent = $('#project-editor').val();
    } else {
        // Otherwise, preserve the existing editorContent from the database
        // This ensures we don't overwrite it when just creating a collection object
        editorContent = currentEditorContent || "";
    }
    
    return {
        _id: collectionId,
        title: title,
        projects: projects,
        editorContent: editorContent,
        // Always provide a createdAt timestamp - either keep existing or use current time
        createdAt: currentCollectionId ? (currentCreatedAt || now) : now,
        lastUpdated: now
    };
}

// Save collection to database
function saveCollectionToDatabase(collection) {
    return $.ajax({
        type: "POST", 
        url: "/api/save-collection",  // This now routes to merge_blueprint
        data: JSON.stringify(collection),
        contentType: "application/json; charset=utf-8",
        dataType: "json"
    });
}

// Function to display all fields with edit functionality in the Merged Table
function mergeformat(d) {
    const isUuidPage = window.location.pathname.match(/\/project\/[^\/]+$/i);
    
    // Generate a project UUID if it's not already in the data
    // Use the new hash-based UUID generation including the project title
    const projectUuid = d[11] || generateProjectUuid(d[0], d[1], d[2], d[4]); // d[4] is the project title
    
    // Create proper project URL
    const projectUrl = `/project/${projectUuid}`;
    const fullUrl = window.location.origin + projectUrl;
    
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td style="vertical-align: top;">Abstract:</td>' +
        '<td class="abstract-content" style="line-height: 1.5;">' + d[8] + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td style="vertical-align: top;">Student Names:</td>' +
        '<td class="student-names-content" style="line-height: 1.5;">' + d[9] + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td style="vertical-align: middle;">Project URL:</td>' +
        '<td>' +
            '<span class="project-url" style="display: none;">' + projectUrl + '</span>' +
            '<a href="' + projectUrl + '" target="_blank" class="project-link" style="color: #0A3B80; text-decoration: underline; font-weight: 500; transition: color 0.2s ease, transform 0.2s ease; display: inline-block;"' + 
            ' onmouseover="this.style.color=\'#0062cc\'; this.style.transform=\'scale(1.02)\'" ' +
            ' onmouseout="this.style.color=\'#0A3B80\'; this.style.transform=\'scale(1)\'">' + 
            fullUrl + '</a>' +
        '</td>' +
        '</tr>' +
        '</table>';
}

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
                "text": 'Share Collection',  // Changed from "Save & Share Collection"
                "className": 'sharing',
                "action": function () {
                    // Just open the collection page for sharing
                    if (currentCollectionId) {
                        window.open(`/collection/${currentCollectionId}`, "_blank");
                    } else {
                        // If no collection ID exists yet, show a message
                        alert("Please merge and save results first before sharing.");
                    }
                }
            },
            {
                "text": 'Add to Editor',  // Changed from "Open in Editor"
                "className": 'open-editor-btn',
                "action": function () {
                    addToEditor();  // Changed function call
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

    // Initialize title functionality
    initializeCurationTitle();
    
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

    // Add this line at the end of the document ready function
    initializeCurationTitle();

    // Add editor toggle button at the bottom of the merged table with proper centering
    $('#example_wrapper').append(`
        <div style="display: flex; justify-content: center; margin-top: 20px; margin-bottom: 15px;">
            <button id="bottom-editor-toggle" class="dt-button buttons-html5" 
                style="background-color: #002856; color: #dbaa00; 
                border: none; border-radius: 2px; 
                padding: 0.5em 1em; font-size: 0.88em;">
                Open Editor
            </button>
        </div>
    `);

    // Add event handler for the toggle button
    $('#bottom-editor-toggle').on('click', function() {
        toggleProjectEditor();
    });
    
    // Add hover effect to match DataTables buttons
    $('#bottom-editor-toggle').on('mouseenter', function() {
        $(this).css({
            'background-color': '#001b3d',
            'cursor': 'pointer'
        });
    }).on('mouseleave', function() {
        $(this).css({
            'background-color': '#002856'
        });
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
                    generateProjectUuid(merged_array[i]["Year-Semester"], merged_array[i]["Class"], merged_array[i]["Team#"], merged_array[i]["Project Title"])
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
                            generateProjectUuid(merged_array[i]["Year-Semester"], merged_array[i]["Class"], merged_array[i]["Team#"], merged_array[i]["Project Title"])
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
                        generateProjectUuid(merged_array[i]["Year-Semester"], merged_array[i]["Class"], merged_array[i]["Team#"], merged_array[i]["Project Title"])
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

            // If all rows are removed, reset the collection
            if (merged_table.rows().count() === 0) {
                resetCurrentCollection();
            }
        });

        // NEW: Save the merged results to the database automatically
        if (merged_table.rows().count() > 0) {
            // Create a collection from the merged table
            const collection = createCollectionFromMergedTable();
            
            // Show saving indicator
            $('.merge').text('Saving...').prop('disabled', true);
            
            // Save the collection to the database
            saveCollectionToDatabase(collection)
                .done(function(data) {
                    // Store the collection ID for future updates
                    currentCollectionId = collection._id;
                    
                    // Store the creation timestamp for future updates
                    if (!currentCreatedAt && collection.createdAt) {
                        currentCreatedAt = collection.createdAt;
                    }
                    
                    // Store the editor content for future reference
                    if (collection.editorContent !== undefined) {
                        currentEditorContent = collection.editorContent;
                    }
                    
                    // Show success message
                    $('.merge').text('Saved!');
                    
                    // Reset button text and update share button text
                    setTimeout(function() {
                        $('.merge').text('Save/Merge Results').prop('disabled', false);
                        $('.sharing').text('Share Collection');
                    }, 2000);
                })
                .fail(function(jqXHR, textStatus, errorThrown) {
                    console.error("Error saving collection:", textStatus, errorThrown);
                    $('.merge').text('Error - Try Again').prop('disabled', false);
                    
                    // Reset button text after error
                    setTimeout(function() {
                        $('.merge').text('Save/Merge Results');
                    }, 3000);
                });
        }
    });

    // Initialize or update the title input
    initializeCurationTitle();

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
});

// Add this function
function resetCurrentCollection() {
    currentCollectionId = null;
    currentCollectionTitle = null;
    currentCreatedAt = null; // Reset creation timestamp
    $('.sharing').text('Save & Share Collection');
    
    // Reset title input if it exists
    if ($('#curation-title').length) {
        $('#curation-title').val('Curated Projects - ' + new Date().toLocaleDateString());
    }
}

// Add this function to create and manage the editable title
function initializeCurationTitle() {
    // Check if title container already exists
    if ($('#curation-title-container').length === 0) {
        // Create title container before the merged table
        const titleHtml = `
            <div id="curation-title-container" class="mb-3" style="margin-bottom: 15px;">
                <div class="d-flex align-items-center">
                    <input type="text" id="curation-title" 
                        class="form-control" 
                        value="${currentCollectionTitle || 'Curated Projects - ' + new Date().toLocaleDateString()}"
                        placeholder="Enter curation title..." 
                        style="font-size: 1.25rem; font-weight: 600; color: #162D4F; width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
                    <button id="save-title-btn" 
                        style="margin-left: 10px; background-color: #162D4F; color: #dbaa00; border: none; padding: 8px 12px; cursor: pointer; border-radius: 4px;">
                        <i class="fa fa-check"></i> Save
                    </button>
                </div>
                <small class="text-muted" style="display: block; margin-top: 5px; font-style: italic;">
                    Edit the curation title above. Changes will be saved when you update the collection.
                </small>
            </div>
        `;
        
        $('.mergeTable').prepend(titleHtml);
        
        // Add event handlers
        addTitleEventHandlers();
    } else {
        // If it already exists, just update value and reattach handlers
        $('#curation-title').val(currentCollectionTitle || 'Curated Projects - ' + new Date().toLocaleDateString());
        addTitleEventHandlers();
    }
}

// Separate function to add event handlers to avoid duplication
function addTitleEventHandlers() {
    // Remove existing handlers first to prevent duplicates
    $('#curation-title').off('input');
    $('#save-title-btn').off('click');
    
    // Add change handler for title field
    $('#curation-title').on('input', function() {
        // Set flag indicating title has been changed
        titleChanged = true;
    });
    
    // Add click handler for save button
    $('#save-title-btn').on('click', function() {
        const newTitle = $('#curation-title').val().trim();
        if (newTitle) {
            currentCollectionTitle = newTitle;
            
            // Create and save the collection with the new title
            const collection = createCollectionFromMergedTable();
            
            // Show saving indicator
            const $btn = $(this);
            $btn.html('<i class="fa fa-spinner fa-spin"></i> Saving...');
            $btn.prop('disabled', true);
            
            // Save to database
            saveCollectionToDatabase(collection)
                .done(function(data) {
                    // Update text in sharing button if collection exists
                    if (currentCollectionId) {
                        $('.sharing').text('Share Collection');
                    }
                    
                    // Show success message
                    $btn.html('<i class="fa fa-check"></i> Saved!');
                    
                    // Add visual feedback
                    $btn.css({
                        'background-color': '#28a745',
                        'color': 'white'
                    });
                    
                    setTimeout(() => {
                        $btn.html('<i class="fa fa-check"></i> Save');
                        $btn.css({
                            'background-color': '#162D4F',
                            'color': '#dbaa00'
                        });
                        $btn.prop('disabled', false);
                    }, 2000);
                })
                .fail(function(jqXHR, textStatus, errorThrown) {
                    console.error("Error saving title:", textStatus, errorThrown);
                    $btn.html('<i class="fa fa-times"></i> Error');
                    $btn.css({
                        'background-color': '#dc3545',
                        'color': 'white'
                    });
                    
                    setTimeout(() => {
                        $btn.html('<i class="fa fa-check"></i> Save');
                        $btn.css({
                            'background-color': '#162D4F',
                            'color': '#dbaa00'
                        });
                        $btn.prop('disabled', false);
                    }, 2000);
                });
        }
    });
    
    // Add hover effects for better UX
    $('#save-title-btn').hover(
        function() {
            $(this).css('background-color', '#0e1d33');
        },
        function() {
            $(this).css('background-color', '#162D4F');
        }
    );
}

// Add this function after the initializeCurationTitle function

// Function to handle opening the project editor with consistent button styling
function openProjectEditor() {
    // Remove existing editor if present
    if ($('#project-editor-container').length > 0) {
        $('#project-editor-container').remove();
    }

    // Create the editor container
    const editorHtml = `
        <div id="project-editor-container" style="margin: 20px; padding: 15px; border: 1px solid #ccc; border-radius: 5px; background-color: #dedede;">
            <h4 style="margin-bottom: 15px; color: #162D4F;">Project Curation Editor</h4>
            <textarea id="project-editor" style="width: 100%; min-height: 400px; padding: 10px; font-family: monospace; color: #000; background-color: #fff; border: 1px solid #aaa; border-radius: 4px; resize: none;"></textarea>
            <div style="margin-top: 15px; text-align: right;">
                <button id="save-edit-btn" style="background-color: #002856; color: #dbaa00; border: none; padding: 10px 20px; border-radius: 4px;">Save Changes</button>
            </div>
        </div>
    `;

    // Append the editor to the DOM
    $('#example_wrapper').after(editorHtml);

    // Set the editor content
    $('#project-editor').val(currentEditorContent || "");

    // Attach event handler for the save button
    $('#save-edit-btn').on('click', function () {
        saveProjectEdits();
    });

    // Update the toggle button text
    $('#bottom-editor-toggle').text('Close Editor');
}

// Function to format projects for the editor - improved with project titles as headers
function formatProjectsForEditor(rowsData) {
    let formattedText = '';
    
    // Loop through each row
    for (let i = 0; i < rowsData.length; i++) {
        const row = rowsData[i];
        const projectUrl = window.location.origin + `/project/${row[11] || generateProjectUuid(row[0], row[1], row[2], row[4])}`;
        const projectTitle = row[4] || `Untitled Project ${i+1}`;
        
        // Format project data with project title as header
        formattedText += `${projectTitle}\n`;
        formattedText += `${'='.repeat(projectTitle.length)}\n`;
        formattedText += `Year-Semester: ${row[0]}\n`;
        formattedText += `Class: ${row[1]}\n`;
        formattedText += `Team #: ${row[2]}\n`;
        formattedText += `Team Name: ${row[3]}\n`;
        formattedText += `Organization: ${row[5]}\n`;
        formattedText += `Industry: ${row[6]}\n`;
        formattedText += `Abstract:\n${row[8]}\n\n`;
        formattedText += `Student Names:\n${row[9]}\n\n`;
        formattedText += `Project URL: ${projectUrl}\n\n`;
        
        // Add separator between projects
        if (i < rowsData.length - 1) {
            formattedText += `\n-------------------------------------------\n\n`;
        }
    }
    
    return formattedText;
}

// Function to save project edits with consistent button styling during state changes
function saveProjectEdits() {
    const editedText = $('#project-editor').val() || "";

    // Update the global editor content variable
    currentEditorContent = editedText;

    // Create the collection object
    const collection = createCollectionFromMergedTable();
    collection.editorContent = editedText;

    // Save the collection to the database
    $('#save-edit-btn').text('Saving...').prop('disabled', true);

    saveCollectionToDatabase(collection)
        .done(function () {
            $('#save-edit-btn').text('Saved!');
            setTimeout(() => {
                $('#save-edit-btn').text('Save Changes').prop('disabled', false);
            }, 2000);
        })
        .fail(function (jqXHR, textStatus, errorThrown) {
            console.error("Error saving edited content:", textStatus, errorThrown);
            $('#save-edit-btn').text('Error - Try Again').prop('disabled', false);
        });
}

/**
 * Toggle the project editor open/closed and update button states
 * Checks for unsaved changes before closing
 */
function toggleProjectEditor() {
    const $topButton = $('.open-editor-btn');
    const $bottomButton = $('#bottom-editor-toggle');
    const isEditorOpen = $('#project-editor-container').length > 0;

    if (isEditorOpen) {
        // Get current content from the editor
        const currentText = $('#project-editor').val() || "";

        // Normalize both strings for comparison
        const normalize = str => (str || "").trim().replace(/\r\n/g, '\n');
        const normalizedCurrent = normalize(currentText);
        const normalizedOriginal = normalize(currentEditorContent);

        // Check if there are unsaved changes
        const hasChanges = normalizedCurrent !== normalizedOriginal;

        if (!hasChanges || confirm('Close editor? Any unsaved changes will be lost.')) {
            // Close the editor
            $('#project-editor-container').remove();
            $topButton.text('Add to Editor');
            $bottomButton.text('Open Editor');
        }
    } else {
        // Open the editor
        if (currentCollectionId) {
            // Fetch the latest content from the database
            $bottomButton.text('Loading...').prop('disabled', true);

            $.ajax({
                type: "GET",
                url: `/api/get-collection/${currentCollectionId}`,
                dataType: "json",
                cache: false // Prevent caching
            })
                .done(function (data) {
                    if (data && data.editorContent !== undefined) {
                        // Update the global editor content variable
                        currentEditorContent = String(data.editorContent || "");
                    } else {
                        currentEditorContent = "";
                    }

                    // Open the editor with the latest content
                    openProjectEditor();
                    $topButton.text('Add to Editor');
                    $bottomButton.text('Close Editor').prop('disabled', false);
                })
                .fail(function (jqXHR, textStatus, errorThrown) {
                    console.error("Error fetching collection data:", textStatus, errorThrown);
                    openProjectEditor(); // Open the editor even if the fetch fails
                    $topButton.text('Add to Editor');
                    $bottomButton.text('Close Editor').prop('disabled', false);
                });
        } else {
            // No collection ID, open an empty editor
            currentEditorContent = "";
            openProjectEditor();
            $topButton.text('Add to Editor');
            $bottomButton.text('Close Editor');
        }
    }
}

/**
 * Add selected or all projects to the editor
 * Appends formatted project data to existing editor content
 * No automatic database save - just puts content in the editor
 */
function addToEditor() {
    // Check if editor is open, if not open it first
    if ($('#project-editor-container').length === 0) {
        toggleProjectEditor();
        
        // Need to wait for the editor to open before continuing
        setTimeout(function() {
            processAddToEditor();
        }, 500); // Short delay to ensure editor is open
    } else {
        processAddToEditor();
    }
    
    // Process the actual add to editor functionality
    function processAddToEditor() {
        // Get selected rows or all rows if none are selected
        const selectedRows = merged_table.rows('.selected').data();
        const rowsToAdd = selectedRows.length > 0 ? selectedRows : merged_table.rows().data();
        
        // Format the selected projects
        const formattedProjects = formatProjectsForEditor(rowsToAdd);
        
        // Get current content from editor directly
        let currentContent = $('#project-editor').val() || "";
        
        // Append new content to existing content
        let newContent;
        if (currentContent.trim() === "") {
            // If there's no existing content, just use the new content
            newContent = formattedProjects;
        } else {
            // Otherwise append with a separator
            newContent = currentContent + "\n\n-------------------------------------------\n\n" + formattedProjects;
        }
        
        // Update the editor with the new content
        $('#project-editor').val(newContent);
        
        // Provide visual feedback that content was added
        $('.open-editor-btn').html('Added!');
        
        // Reset button after a delay
        setTimeout(function() {
            $('.open-editor-btn').html('Add to Editor');
        }, 2000);
        
        // Flash the editor to highlight the change
        $('#project-editor').css('background-color', '#f8f9d4');
        setTimeout(function() {
            $('#project-editor').css('background-color', '#fff');
        }, 500);
    }
}