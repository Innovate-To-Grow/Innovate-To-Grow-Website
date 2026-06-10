function format(d) {
    // `d` is the original data object for the row
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td><b>Abstract:</b></td>' +
        '<td>' + escapeSheetText(d.Abstract) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Student Names:</b></td>' +
        '<td>' + escapeSheetText(d["Student Names"]) + '</td>' +
        '</tr>' +
        '</table>';
}

var datas = [];
var test;
$(document).ready(function () {
    $.getJSON("/api/sheets/10_l1AyeiwCN8GZl6CfL6CwOwVH6K66zmrZd1xxVx7qk/values/2021-01-Spring-I2G-WEB", function (data) {
        var length = data.values.length;
        console.log(length);
        for (var i = 1; i < length; i++) {
            const subArray = data.values[i];
            subdata = {
                "Track": subArray[0],
                "Year-Semester": subArray[1],
                "Class": subArray[2],
                "Team#": subArray[3],
                "Team Name": subArray[4],
                "Project Title": subArray[5],
                "Organization": subArray[6],
                "Industry": subArray[7],
                "Abstract": subArray[8],
                "Student Names": subArray[9],
                "Buttons": subArray[10],
                "NameTitle": subArray[11],
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
            {"data": "Track", "render": sheetTextRenderer},
            {"data": "Year-Semester", "render": sheetTextRenderer},
            {"data": "Class", "render": sheetTextRenderer},
            {"data": "Team#", "render": sheetTextRenderer},
            {"data": "Team Name", "render": sheetTextRenderer},
            {"data": "Project Title", "render": sheetTextRenderer},
            {"data": "Organization", "render": sheetTextRenderer},
            {"data": "Industry", "render": sheetTextRenderer},
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "defaultContent": ''
            },
            {
                "data": "Abstract",
                "render": sheetTextRenderer,
                "bVisible": false
            },
            {
                "data": "Student Names",
                "render": sheetTextRenderer,
                "bVisible": false
            }
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
            tr.css('color', 'Black');
            tr.css('font-weight', 'normal');
        } else {
            // Open this row
            row.child(format(row.data())).show();
            tr.addClass('shown');
            tr.css('color', '#162D4F');
            tr.css('font-weight', 'bold');
        }
    });
};
