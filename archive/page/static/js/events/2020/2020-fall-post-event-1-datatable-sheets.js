function format(d) {
    // `d` is the original data object for the row
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td><b>Track:</b></td>' +
        '<td>' + escapeSheetText(d.Track) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Class:</b></td>' +
        '<td>' + escapeSheetText(d.Class) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Team#:</b></td>' +
        '<td>' + escapeSheetText(d["Team#"]) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Team Name:</b></td>' +
        '<td>' + escapeSheetText(d["Team Name"]) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Students Names:</b></td>' +
        '<td>' + escapeSheetText(d["Student Names"]) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Project Title:</b></td>' +
        '<td>' + escapeSheetText(d["Project Title"]) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Organization:</b></td>' +
        '<td>' + escapeSheetText(d.Organization) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Summary:</b></td>' +
        '<td>' + escapeSheetText(d["Short Summary"]) + '</td>' +
        '</tr>'
    '</table>';
}

var datas = [];
var test;
$(document).ready(function () {
    $.getJSON("/api/sheets/1TJZfQFYf0iw1SBcqrdnS_efOsFzIppMg1aOajE-atc4/values/Sheet1", function (data) {
        var length = data.values.length;
        console.log(length);
        for (var i = 1; i < length; i++) {
            const subArray = data.values[i];
            subdata = {
                "Class": subArray[0],
                "Team#": subArray[1],
                "Track": subArray[2],
                "Project Title": subArray[3],
                "Organization": subArray[4],
                "Team Name": subArray[5],
                "Short Summary": subArray[6],
                "Student Names": subArray[7],
                "Student Emails": subArray[8],
                "Buttons": subArray[9],
            };
            JSON.stringify(subdata);
            datas.push(subdata);
        }
        console.log("first");
        fnLoadDataTableInstance()
    });

});

function fnLoadDataTableInstance() {
    // #example refers to the html table, 'id="example"'
    console.log("second");
    var sheetTextRenderer = $.fn.dataTable.render.text();
    var table = $('#example').DataTable({
        dom: 'Bfrtip',
        pageLength: 10,
        search: {
            search: document.location.search.replace(/^.*?\=/, '')
        },
        data: datas,
        columns: [
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "defaultContent": ''
            },
            {"data": "Track", "render": sheetTextRenderer},
            {"data": "Class", "render": sheetTextRenderer},
            {"data": "Team#", "render": sheetTextRenderer},
            {"data": "Team Name", "render": sheetTextRenderer},
            {"data": "Project Title", "render": sheetTextRenderer},
            {"data": "Organization", "render": sheetTextRenderer},

        ],
        order: [
            [1, 'desc']
        ],
        fixedHeader: {
            header: true,
            footer: true
        }
    });
    $('#example tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = table.row(tr);
        if (row.child.isShown()) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        } else {
            // Open this row
            row.child(format(row.data())).show();
            tr.addClass('shown');
        }
    });
};
