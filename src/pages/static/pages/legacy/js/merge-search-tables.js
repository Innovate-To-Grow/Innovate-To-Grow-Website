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
var datas = [];
var share_datas = [];
var uuid;
var unique_url = false;
// global variable END

// Prep START
$(document).ready(function () {
    // get the team_names and team_numbers from the html
    team_names = JSON.parse(document.getElementById("data").dataset.team_names);
    team_numbers = JSON.parse(document.getElementById("data").dataset.team_numbers);

    $.getJSON("https://sheets.googleapis.com/v4/spreadsheets/1KATiK1Fnlb7Vsd186mCbaGjhID-OUGN-1QHWY8hIc5U/values/Past-Projects-WEB-LIVE?alt=json&key=AIzaSyDWhIC7QQal9etKiwUDzs34yugQR0KqS94", function (data) {
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

// Set the format of Abstract and Student Name when the button is clicked for Search Tables
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

// Set the format of Abstract and Student Name when the button is clicked for Merge Table
function mergeformat(d) {
    // `d` is the original data object for the row
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td>Abstract:</td>' +
        '<td>' + d[8] + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td>Student Names:</td>' +
        '<td>' + d[9] + '</td>' +
        '</tr>' +
        '</table>';
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
                "text": 'Get Shareable URL',
                "className": 'sharing',
                "action": function () {
                    $('#share').click();
                    $('#share').remove();
                    $('.sharing').text('Loading...');
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
                "action": function () {
                    $('#example').find('td.details-control-merge').each(function () {
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
                "bVisible": false
            },
            {
                "bVisible": false
            },
            {
                "data": null,
                "className": "dt-center editor-delete",
                "defaultContent": '<i class="fa fa-trash"/>',
                "orderable": false
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
            //change color of text to tell user that the row is assosiated to the abstract and student name
            tr.css('color', '#162D4F');
            tr.css('font-weight', 'bold');
        }
    });

});
// Merge Table specific functions END
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
// All functions under the search table scope (.addtable) START
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

    // Merge results function START
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
    // Merge results function END

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
        var share_array = merged_table.rows().data().toArray();
        var length = share_array.length;
        for (var i = 0; i < length; i++) {
            const subArray = share_array[i];
            subdata = {
                "Year-Semester": subArray[0],
                "Class": subArray[1],
                "Team#": subArray[2],
                "Team Name": subArray[3],
                "Project Title": subArray[4],
                "Organization": subArray[5],
                "Industry": subArray[6],
                "Abstract": subArray[8],
                "Student Names": subArray[9],
            };
            JSON.stringify(subdata);
            share_datas.push(subdata);
        }

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
});
