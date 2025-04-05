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
var datas = [];  // where all the data from the Google sheet is stored
var share_datas = [];
let userId = null;
var uuid;
var unique_url = false;
var currentCollectionId = null; // Tracks the current collection ID
var currentCollectionTitle = null; // Tracks the current collection title
var titleChanged = false; // Flag to track if title has been edited
var currentCreatedAt = null; // Tracks the original creation timestamp
let currentEditorContent = ""; // Tracks the current editor content
// global variables END

// Prep START
$(document).ready(function () {
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
    });

    document.getElementById("rowdelete").disabled = true;
    document.getElementById("rowkeep").disabled = true;
    $("#rowkeep").addClass('gray');
    $("#rowdelete").addClass('gray');
    $(".mergeTable").hide();

    setTimeout(function () {
        $('.addtable').click();
        $('.loader').hide();
        $(".mergeTable").show();
    }, 2500);

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

// Function to generate a UUID for projects that's consistent across saves
function generateProjectUuid(yearSemester, classCode, teamNumber, projectTitle) {
    const seed = `${yearSemester}-${classCode}-${teamNumber}-${projectTitle}`;
    let hash = 0;
    for (let i = 0; i < seed.length; i++) {
        const char = seed.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash;
    }
    return `proj-${Math.abs(hash).toString(16)}`;
}

// Generate a collection ID that uses MongoDB-compatible format
function generateCollectionId() {
    return `coll_${new Date().getTime()}_${Math.floor(Math.random() * 10000)}`;
}

// Create collection object from merged table to save to MongoDB
function createCollectionFromMergedTable() {
    const tableData = merged_table.rows().data().toArray();

    // Create projects array with consistent UUIDs
    const projects = tableData.map(row => {
        // Generate or use existing UUID
        const uuid = row[11] || generateProjectUuid(row[0], row[1], row[2], row[4]);

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

    // Use existing collection ID or generate a new one
    const collectionId = currentCollectionId || generateCollectionId();

    // Get title from input field or use default
    const title = $('#curation-title').length
    ? $('#curation-title').text().trim()
    : (currentCollectionTitle || 'Curated Projects - ' + new Date().toLocaleDateString());

    // Timestamps for collection tracking
    const now = new Date().toISOString();

    // Handle editor content properly
    let editorContent = currentEditorContent;

    // Only update editor content if explicitly called from saveProjectEdits
    if (new Error().stack.includes('saveProjectEdits') && $('#project-editor').length) {
        editorContent = $('#project-editor').val() || "";
    }

    // Fetch user ID from the server
    $.ajax({
        type: "GET",
        url: "/get_user_id",
        async: false,
        success: function (response) {
            if (response && response.id) {
                userId = response.id;
            } else {
                console.error("User ID not found in response:", response);
            }
        },
        error: function (jqXHR, textStatus, errorThrown) {
            console.error("Error fetching user ID:", textStatus, errorThrown);
        }
    });

    return {
        _id: collectionId,
        userId: userId,
        title: title,
        projects: projects,
        editorContent: editorContent,
        createdAt: now,
    };
}

function saveCollectionToDatabase(collection) {
    return $.ajax({
        type: "POST", 
        url: "/api/save-collection",
        data: JSON.stringify(collection),
        contentType: "application/json; charset=utf-8",
        dataType: "json",
        success: function(response) {
            if (response.success) {
                if (response.redirect) {
                    window.location.href = response.redirect;  // Redirecting user
                } else {
                    console.log("Collection updated successfully!");
                }
            } else {
                console.error("Failed to save collection:", response.message);
            }
        },
        error: function(xhr, status, error) {
            console.error("Error occurred while saving:", error);
        }
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
    const urlParams = new URLSearchParams(window.location.search);
    const collectionParam = urlParams.get('collection');
    const tableElement = $('.display');

    function initializeMergedTable(tableData = []) {
        merged_table = tableElement.DataTable({
            data: tableData,
            dom: 'lBfrtip',
            language: {
                emptyTable: "No entries have been saved yet."
            },
            buttons: [
                {
                    extend: 'collection',
                    text: 'Export',
                    className: 'export-dropdown',
                    buttons: [
                        {
                            extend: 'csv',
                            text: 'CSV'
                        },
                        {
                            extend: 'excel',
                            text: 'XLSX'
                        },
                        {
                            text: 'PDF',
                            className: 'export-pdf',
                            action: function(e, dt, node, config) {
                                try {
                                    console.log('Export PDF button clicked');
                                    const collection = createCollectionFromMergedTable();
                                    console.log('Collection data created:', collection);
                                    exportToPDF(collection);
                                } catch (error) {
                                    console.error('Error in Export PDF button handler:', error);
                                    alert('Error preparing PDF export. Check console for details.');
                                }
                            }
                        }
                    ]
                },
                {
                    text: 'Share Collection',
                    className: 'sharing',
                    action: function () {
                        if (currentCollectionId) {
                            window.open(`/collection/${currentCollectionId}`, "_blank");
                        } else {
                            alert("Please merge and save results first before sharing.");
                        }
                    }
                },
                {
                    text: 'Show Details',
                    className: 'details-toggle-btn',
                    action: function () {
                        const $button = $('.details-toggle-btn');
                        const isShowing = $button.text() === 'Hide Details';

                        $('#example').find('td.details-control-merge').each(function () {
                            const tr = $(this).closest('tr');
                            const row = merged_table.row(tr);

                            if (isShowing) {
                                if (row.child.isShown()) {
                                    row.child.hide();
                                    tr.removeClass('shown');
                                    tr.css('color', 'Black').css('font-weight', 'normal');
                                }
                            } else {
                                if (!row.child.isShown()) {
                                    row.child(mergeformat(row.data())).show();
                                    tr.addClass('shown');
                                    tr.css('color', '#162D4F').css('font-weight', 'bold');
                                }
                            }
                        });

                        $button.text(isShowing ? 'Show Details' : 'Hide Details');
                    }
                }
            ],
            pageLength: 5,
            lengthMenu: [[5, 10, 25, 100], [5, 10, 25, 100]],
            search: {
                search: ""
            },
            aoColumns: [
                {}, {}, {}, {}, {}, {}, {},
                {
                    className: 'details-control-merge',
                    orderable: false,
                    mDataProp: "null",
                    defaultContent: ''
                },
                { bVisible: false }, // Abstract
                { bVisible: false }, // Student Names
                {
                    data: null,
                    className: "dt-center editor-delete",
                    defaultContent: '<i class="fa fa-trash"/>',
                    orderable: false
                },
                { bVisible: false, data: null } // UUID
            ],
            order: [[1, 'asc']],
            fixedHeader: {
                header: true,
                footer: true
            }
        });

        // Handle row expansion for details
        $('#example').on('click', 'td.details-control-merge', function () {
            const tr = $(this).closest('tr');
            const row = merged_table.row(tr);
            if (row.child.isShown()) {
                row.child.hide();
                tr.removeClass('shown').css({ color: 'Black', fontWeight: 'normal' });
            } else {
                row.child(mergeformat(row.data())).show();
                tr.addClass('shown').css({ color: '#162D4F', fontWeight: 'bold' });
            }
        });

        // Add editor toggle button
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

        $('#bottom-editor-toggle').on('click', function () {
            toggleProjectEditor();
        }).on('mouseenter', function () {
            $(this).css({ backgroundColor: '#001b3d', cursor: 'pointer' });
        }).on('mouseleave', function () {
            $(this).css({ backgroundColor: '#002856' });
        });

        // Init helper functions
        initializeCurationTitle();
        initializeShareButtons();
    }

    if (collectionParam) {
        console.log("Collection ID from URL:", collectionParam);
        currentCollectionId = collectionParam;

        $.ajax({
            type: "GET",
            url: `/api/get-collection/${currentCollectionId}`,
            dataType: "json"
        }).done(function (data) {
            console.log("Loaded collection data on page init:", data);

            if (data) {
                currentEditorContent = data.editorContent || "";
                currentCollectionTitle = data.title || "Untitled Collection";
                currentCreatedAt = data.createdAt || new Date().toISOString();

                const tableData = (data.projects || []).map(project => [
                    project.year_semester || '',
                    project.class || '',
                    project.team_number || '',
                    project.team_name || '',
                    project.project_title || '',
                    project.organization || '',
                    project.industry || '',
                    '', // Details
                    project.abstract || '',
                    project.student_names || '',
                    '', // Delete
                    project.uuid || ''
                ]);

                initializeMergedTable(tableData);

                if ($('#project-editor').length) {
                    $('#project-editor').val(currentEditorContent);
                }
            }
        }).fail(function (error) {
            console.error("Failed to load collection, fallback to empty table:", error);
            // If collection ID in ?collection= does not exist in database redirect user to base past projects page
            window.location.href = "/past-projects"
        });
    } else {
        console.log("No collection ID in URL, initializing a new collection.");
        currentCollectionTitle = 'Curated Projects - ' + new Date().toLocaleDateString();
        currentEditorContent = '';
        currentCreatedAt = new Date().toISOString();
        initializeMergedTable([]);
    }
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
            "search": ""
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

            // Update the database with the new state of the merged table
            const collection = createCollectionFromMergedTable();

            saveCollectionToDatabase(collection)
                .done(function () {
                    console.log("Database updated successfully after merging rows.");
                })
                .fail(function (jqXHR, textStatus, errorThrown) {
                    console.error("Error updating database after merging rows:", textStatus, errorThrown);
                });
        } else {
            if (confirmation_tracker == 0) { // if its a fresh start, makes sure to ask for confirmation only once per press
                if (confirm("Do you want to merge all of your search tables?")) {
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
                    // Update the database with the new state of the merged table
                    const collection = createCollectionFromMergedTable();

                    saveCollectionToDatabase(collection)
                        .done(function () {
                            console.log("Database updated successfully after merging rows.");
                        })
                        .fail(function (jqXHR, textStatus, errorThrown) {
                            console.error("Error updating database after merging rows:", textStatus, errorThrown);
                        });
                } else {
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
            // Delete row in merged_table and update deleted array
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
        
            // If all rows are removed, reset the collection metadata
            if (merged_table.rows().count() === 0) {
                resetCurrentCollection();
            }
        
            // Update the database with the new state of the merged table
            const collection = createCollectionFromMergedTable();
        
            saveCollectionToDatabase(collection)
                .done(function () {
                    console.log("Database updated successfully after row deletion.");
                })
                .fail(function (jqXHR, textStatus, errorThrown) {
                    console.error("Error updating database after row deletion:", textStatus, errorThrown);
                });
        });
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
        // Set the default title if no title exists
        if (!currentCollectionTitle) {
            currentCollectionTitle = 'Curated Projects - ' + new Date().toLocaleDateString();
        }

        // Create title container and place it within the Saved Merged Results section
        const titleHtml = `
            <div id="curation-title-container" style="margin-top: 15px; text-align: center;">
                <h3 id="curation-title" 
                    contenteditable="true" 
                    style="display: inline-block; font-size: 1.5rem; font-weight: 600; color: #162D4F; margin: 0; padding: 5px 10px; border: 1px solid transparent; border-radius: 4px; background-color: #f9f9f9; transition: border-color 0.2s ease; cursor: pointer;">
                    ${currentCollectionTitle}
                </h3>
                <small class="text-muted" style="display: block; margin-top: 5px; font-style: italic;">
                    Double-click the title to edit. Press Enter to save or click away to cancel.
                </small>
            </div>
        `;

        // Append the title container below the "Saved Merged Results" text
        $('.mergeTable').before(titleHtml);

        // Add event handlers
        addTitleEventHandlers();
    } else {
        // If it already exists, just update the value and reattach handlers
        $('#curation-title').text(currentCollectionTitle || 'Curated Projects - ' + new Date().toLocaleDateString());
        addTitleEventHandlers();
    }
}

// Separate function to add event handlers to avoid duplication
function addTitleEventHandlers() {
    const $title = $('#curation-title');
    let originalTitle = currentCollectionTitle || 'Curated Projects - ' + new Date().toLocaleDateString();

    // Enable editing on double-click
    $title.off('dblclick').on('dblclick', function () {
        $(this).attr('contenteditable', 'true').focus();
        $(this).css('border', '1px solid #162D4F'); // Highlight the border to indicate edit mode
    });

    // Save title on pressing Enter
    $title.off('keydown').on('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault(); // Prevent a new line from being added
            saveTitle($(this));
        }
    });

    // Restore original title if clicked away without saving
    $title.off('blur').on('blur', function () {
        if ($(this).attr('contenteditable') === 'true') {
            $(this).text(originalTitle); // Restore the original title
            $(this).attr('contenteditable', 'false');
            $(this).css('border', '1px solid transparent'); // Remove the border
        }
    });

    // Function to save the title
    function saveTitle($titleElement) {
        const newTitle = $titleElement.text().trim();
        if (newTitle) {
            originalTitle = newTitle; // Update the original title
            currentCollectionTitle = newTitle;
        } else {
            // If no title is provided, use the default title
            currentCollectionTitle = 'Curated Projects - ' + new Date().toLocaleDateString();
            $titleElement.text(currentCollectionTitle);
        }

        // Create the collection object
        const collection = createCollectionFromMergedTable();
        collection.title = currentCollectionTitle; // Update the title

        // Save to database
        saveCollectionToDatabase(collection)
            .done(function () {
                console.log('Title saved successfully:', currentCollectionTitle);
            })
            .fail(function (jqXHR, textStatus, errorThrown) {
                console.error('Error saving title:', textStatus, errorThrown);
            });

        $titleElement.attr('contenteditable', 'false');
        $titleElement.css('border', '1px solid transparent'); // Remove the border
    }
}

// Add this function after the initializeCurationTitle function

// Function to handle opening the project editor with consistent button styling
function openProjectEditor() {
    // Remove existing editor if present
    if ($('#project-editor-container').length > 0) {
        $('#project-editor-container').remove();
    }

    // Create the editor container with the "Add to Editor" and "Save Changes" buttons centered
    const editorHtml = `
        <div id="project-editor-container" style="margin: 20px; padding: 15px; border: 1px solid #ccc; border-radius: 5px; background-color: #dedede; box-sizing: border-box;">
            <h3 style="margin-bottom: 15px; color: #162D4F; text-align: center; font-size: 1.5rem; font-weight: 600;">
                Project Curation Editor
            </h3>
            <div style="text-align: center; margin-bottom: 15px;">
                <button id="add-to-editor-btn" style="background-color: #002856; color: #dbaa00; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer;">
                    Add Curation Detail to Editor
                </button>
            </div>
            <textarea id="project-editor" style="width: 100%; min-height: 400px; padding: 15px; font-family: monospace; color: #000; background-color: #fff; border: 1px solid #aaa; border-radius: 4px; resize: none; box-sizing: border-box;"></textarea>
            <div style="margin-top: 15px; text-align: center;">
                <button id="save-edit-btn" style="background-color: #002856; color: #dbaa00; border: none; padding: 10px 20px; border-radius: 4px;">Save Changes</button>
            </div>
        </div>
    `;

    // Append the editor to the DOM
    $('#example_wrapper').after(editorHtml);

    // Set the editor content
    $('#project-editor').val(currentEditorContent || "");

    // Attach event handler for the "Add to Editor" button
    $('#add-to-editor-btn').on('click', function () {
        addToEditor();
    });

    // Attach event handler for the "Save Changes" button
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
                    // If collection ID in ?collection= does not exist in database redirect user to base past projects page
                    window.location.href = "/past-projects"
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


function exportToPDF(collection) {
    console.log('Starting PDF export...');
    console.log('Collection data:', collection);

    try {
        // Check if pdfMake is available
        if (typeof pdfMake === 'undefined') {
            throw new Error('pdfMake library not loaded');
        }

        console.log('Creating document definition...');
        const docDefinition = {
            pageSize: 'A4',
            pageMargins: [40, 100, 40, 60],
            header: {
                margin: [40, 20, 40, 20],
                columns: [
                    {
                        text: 'Innovate to Grow',
                        alignment: 'center',
                        fontSize: 16,
                        bold: true,
                        color: '#162D4F'
                    }
                ]
            },
            footer: function(currentPage, pageCount) {
                return {
                    margin: [40, 0, 40, 0],
                    columns: [
                        { text: 'Generated on: ' + new Date().toLocaleDateString(), alignment: 'left' },
                        { text: `Page ${currentPage} of ${pageCount}`, alignment: 'right' }
                    ]
                };
            },
            content: [
                {
                    text: collection.title || 'Project Collection',
                    style: 'collectionTitle',
                    margin: [0, 0, 0, 20]
                }
            ],
            styles: {
                collectionTitle: {
                    fontSize: 28,
                    bold: true,
                    color: '#162D4F',
                    alignment: 'center'
                },
                projectTitle: {
                    fontSize: 22,
                    bold: true,
                    color: '#162D4F',
                    margin: [0, 15, 0, 10]
                },
                sectionHeader: {
                    fontSize: 16,
                    bold: true,
                    color: '#162D4F',
                    margin: [0, 15, 0, 10]
                },
                normalText: {
                    fontSize: 12,
                    margin: [0, 5, 0, 10]
                },
                abstractText: {
                    fontSize: 12,
                    margin: [0, 10, 0, 10],
                    lineHeight: 1.4
                }
            }
        };

        // Add projects to content
        collection.projects.forEach((project, index) => {
            try {
                docDefinition.content.push(
                    // Project Title
                    {
                        text: project.project_title,
                        style: 'projectTitle'
                    },
                    // Project Metadata
                    {
                        table: {
                            widths: ['*', '*'],
                            body: [
                                [
                                    { text: `Year-Semester: ${project.year_semester}`, style: 'normalText' },
                                    { text: `Class: ${project.class}`, style: 'normalText' }
                                ],
                                [
                                    { text: `Team: ${project.team_number} - ${project.team_name}`, colSpan: 2, style: 'normalText' }
                                ],
                                [
                                    { text: `Organization: ${project.organization}`, style: 'normalText' },
                                    { text: `Industry: ${project.industry}`, style: 'normalText' }
                                ]
                            ]
                        },
                        layout: 'lightHorizontalLines',
                        margin: [0, 10, 0, 20]
                    },
                    // Abstract Section
                    {
                        text: 'Abstract',
                        style: 'sectionHeader'
                    },
                    {
                        text: project.abstract,
                        style: 'abstractText'
                    },
                    // Student Team Section
                    {
                        text: 'Student Team',
                        style: 'sectionHeader'
                    },
                    {
                        text: project.student_names,
                        style: 'normalText',
                        margin: [0, 10, 0, 20]
                    }
                );

                // Add page break if not the last project
                if (index < collection.projects.length - 1) {
                    docDefinition.content.push({ text: '', pageBreak: 'after' });
                }

            } catch (projectError) {
                console.error(`Error processing project ${index + 1}:`, projectError);
            }
        });

        console.log('Generating PDF...');
        // Generate filename
        const filename = collection.title
            ? collection.title.replace(/[^a-z0-9]/gi, '_').toLowerCase() + '.pdf'
            : 'project_collection.pdf';

        console.log('Creating PDF with filename:', filename);
        // Create and download PDF
        pdfMake.createPdf(docDefinition).download(filename);
        console.log('PDF generation completed');

    } catch (error) {
        console.error('PDF Export Error:', error);
        console.error('Error Stack:', error.stack);
        alert(`Error generating PDF: ${error.message}. Check console for details.`);
    }
}
