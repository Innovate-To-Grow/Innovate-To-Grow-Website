function format(d) {
    // `d` is the original data object for the row
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td><b>Abstract:</b></td>' +
        '<td>' + d.Abstract + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td><b>Student Names:</b></td>' +
        '<td>' + d["Student Names"] + '</td>' +
        '</tr>' +
        '</table>';
}

var datas = [];
var test;
$(document).ready(function () {
    $.getJSON("/api/sheets/1dZADXdBWnRw-EO-2pL3DuuNfFODqIzUflQ6yjyH_pUo/values/2021-01-Fall-I2G-WEB", function (data) {
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
    var table = $('#example').DataTable({
        dom: 'Bfrtip',
        pageLength: 10,
        search: {
            search: document.location.search.replace(/^.*?\=/, '')
        },
        data: datas,
        columns: [
            {"data": "Track"},
            {"data": "Year-Semester"},
            {"data": "Class"},
            {"data": "Team#"},
            {"data": "TeamName"},
            {"data": "Project Title"},
            {"data": "Organization"},
            {"data": "Industry"},
            {
                "className": 'details-control',
                "orderable": false,
                "data": null,
                "defaultContent": ''
            },
            {
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
