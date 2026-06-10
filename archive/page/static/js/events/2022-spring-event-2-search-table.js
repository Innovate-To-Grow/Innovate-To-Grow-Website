function format(d) {
    // `d` is the original data object for the row

    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td>Abstract:</td>' +
        '<td>' + escapeSheetText(d.Abstract) + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td>Student Names:</td>' +
        '<td>' + escapeSheetText(d["Student Names"]) + '</td>' +
        '</tr>' +
        '</table>';
}

var datas = [];
var test;
$(document).ready(function () {
    $.getJSON("/api/sheets/13Yds-sPSPjLSWYyCyIaHauTZ3lchGiNH1n-II6tJOMM/values/2022-01-Spring-I2G-WEB", function (data) {
        var length = data.values.length;
        console.log(length);
        for (var i = 1; i < length; i++) {
            const subArray = data.values[i];
            subdata = {
                "Track": subArray[0],
                "Order": subArray[1],
                "Year-Semester": subArray[2],
                "Class": subArray[3],
                "Team#": subArray[4],
                "TeamName": subArray[5],
                "Project Title": subArray[6],
                "Organization": subArray[7],
                "Industry": subArray[8],
                "Abstract": subArray[9],
                "Student Names": subArray[10],
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
            {"data": "TeamName", "render": sheetTextRenderer},
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
            //   td.css('background-color', 'White');
        } else {
            // Open this row
            row.child(format(row.data())).show();
            tr.addClass('shown');
            tr.css('color', '#162D4F');
            tr.css('font-weight', 'bold');
            //   td.css('background-color', 'Red');
        }
    });
};
