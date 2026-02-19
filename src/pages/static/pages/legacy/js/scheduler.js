function format(d) {
    // `d` is the original data object for the row

    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td>Abstract:</td>' +
        '<td>' + d.Abstract + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td>Student Names:</td>' +
        '<td>' + d["Student Names"] + '</td>' +
        '</tr>' +
        '</table>';
}
var datas = [];
// Pulls data from "2023-08-Fall-I2G-WEB" spreadsheet.
// This data is for the datatables
$(document).ready(function () {
    $.getJSON("https://sheets.googleapis.com/v4/spreadsheets/1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik/values/A1:Y76?alt=json&key=AIzaSyDWhIC7QQal9etKiwUDzs34yugQR0KqS94", function (data) {
        var length = data.values.length;
        for (var i = 1; i < length; i++) {
            const subArray = data.values[i];
            // Only include rows with Year-Semester = "2025-2 Fall"
            if (subArray[2] !== "2025-2 Fall") {
                continue;
            }
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
        fnLoadDataTableInstance()
    });

});
// to load the datatables
function fnLoadDataTableInstance() {
    // #example refers to the html table, 'id="example"'
    var table = $('#example').DataTable({
        // dom: 'Bfrltip',
        pageLength: 10,
        search: {
            search: document.location.search.replace(/^.*?\=/, '')
        },
        data: datas,
        columns: [
            { "data": "Order"},
            { "data": "Track" },
            { "data": "Year-Semester" },
            { "data": "Class" },
            { "data": "Team#" },
            { "data": "TeamName" },
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
                "data": "Abstract",
                "bVisible": false
            },
            {
                "data": "Student Names",
                "bVisible": false
            }
        ],
        order: [
            [1, 'dec']
        ],
        // track: [
        //     [1, 'dec']
        // ],
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

function passvalue(slot) {
    let teamNum = document.getElementById(slot).innerHTML;
    let final = "";
    for (let i = 0; i < 3; i++) {
        final += teamNum[i];
    }

    window.document.location = window.location.pathname + '?value=' + final + '#projects';
}

// the layout of the table is as follows:
//            _ _ _ _ # of Track
// # of order|
//           |
//           |
//           |

// the amount of tracks for CAP
let totalTrackForCAP = 2;
// the amount of order for CAP
let totalOrderForCAP = 6;
// the time start for CAP
let timestartForCAP = "1:00";
// time per slot for CAP
let timePerSlotForCAP = "30";

// the amount of tracks for CEE
let totalTrackForCEE = 1;
// the amount of order for CEE
let totalOrderForCEE = 4;
// the time start for CEE
let timestartForCEE = "1:00";
// time per slot for CEE
let timePerSlotForCEE = "30";

// the amount of tracks for CSE
let totalTrackForCSE = 2;
// the amount of order for CSE
let totalOrderForCSE = 10;
// the time start for CSE
let timestartForCSE = "1:00";
// time per slot for CSE
let timePerSlotForCSE = "20";

let totalRooms = totalTrackForCAP + totalTrackForCEE + totalTrackForCSE; // totalRooms = totalTrackForCAP + totalTrackForCEE + totaltrackForCSE

function getTime(time, addMinute){
    let [h,m] = time.split(":");
    m = parseInt(m) + parseInt(addMinute);
    if (m >= 60){
        h = parseInt(h) + 1;
        m = m - 60;
    }
    if (m < 10){
        m = "0" + m;
    }
    if (h > 12){
        h = h - 12;
    }
    return h + ":" + m;
}

$(document).ready(function () {
    if (totalTrackForCAP > 0) {
        var html =
            '<div class= "span7"> '+
                '<div>&nbsp;</div>'+
                '<div style="text-align: center; color: #002856;"><strong>Engineering Capstone (CAP)</strong></div>'+
                '<section class="center">'+
                    '<div class="table__wrapper">'+
                        '<table class="table" style="width: 100%;">'+
                            '<thead></thead>'+
                            '<tbody>'+
                                '<tr class="roomCAP">'+
                                    '<th scope="col" style="background-color: #efefef; color: #002856; text-align: center;">Room:</th>'+
                                '</tr>'+
                                // '<tr class="zoomCAP">'+
                                //     '<th scope="col" style="background-color: #efefef;">'+
                                //         '<gg-icon class="gg-camera" scope="col" style="align-content: center; margin-top: 13px;"></gg-icon>'+
                                //     '</th>'+
                                // '</tr>'+
                                '<tr class="trackCAP">'+
                                    '<th scope="col" style="background-color: #efefef;">&nbsp;</th>'+
                                '</tr>'+
                            '</tbody>'+
                            '<tbody class="classCAP">'+
                            '<tr>'+
                            '<th class="borderLess" style="background-color: #efefef;">&nbsp;</th>'+
                            '<td data-header="Track 1" style="color: #002856;">'+
                                '<p style="color:#002856; font-weight: bolder;">'+
                                    '<b>FoodTech</b>'+
                                '</p>'+
                            '</td>'+
                            '<td data-header="Track 2" style="color: #002856;">'+
                                '<p style="color:#002856; font-weight: bolder;">'+
                                    '<b>Precision</b>'+
                                '</p>'+
                            '</td>'+
                        '</tr>'+
                            '</tbody>'+
                        '</table>'+
                    '</div>'+
                '</section>'+
            '</div>';
        $(".capTable").append(html);
        for(let i = 0; i < totalTrackForCAP; i++){
            $(".roomCAP").append('<th class="roomt'+(i+1)+'" scope="col" style="background-color: #efefef; color: #002856; text-align: center; font-weight: normal;">&nbsp;</th>');
            $(".zoomCAP").append('<th class="zoomborder" scope="col">'+
                '<a class="zoom" id="zoomt'+(i+1)+'" scope="col" target="_blank" title="Zoom link activated 10 minutes before start!">'+
                    '<span>'+
                        '<strong style="text-decoration: none;">Zoom ' + (i+1) + ' </strong> '  +
                    '</span>'+
                '</a>'+
            '</th>');
            $(".trackCAP").append('<th scope="col" style="background-color: #efefef; color: #002856; text-align: center;">Track ' + (i+1) + '</th>');
        }
        let CAPhtml = "";
        for(let i = 0; i < totalOrderForCAP; i++){
            CAPhtml += '<tr>' +
                '<th class="borderLess" scope="row" style="background-color: #efefef; color: #002856;">'+
                    timestartForCAP +
                '</th>';
            for(let j = 0; j < totalTrackForCAP; j++){
                CAPhtml += '<td data-header="Track ' + (j+1) + '" id="hover' + (i+1) + (j+1) + '"><button class="capr' + (i+1) + 't' + (j+1) + '" id="slot' + (i+1) + (j+1) + '" onclick="passvalue(\'slot' + (i+1) + (j+1) + '\')" style="color: #002856;"></button>'+
                '<p class="caporgr' + (i+1) + 't' + (j+1) + ' companyName">&nbsp;</p>'+
                '</td>';
            }
            CAPhtml += '</tr>';
            timestartForCAP = getTime(timestartForCAP, timePerSlotForCAP);
        }
        CAPhtml += '<tr></tr>';
        $(".classCAP").append(CAPhtml);
    }
    if (totalTrackForCEE > 0) {
        var html =
            '<div class= "span4" style="margin-left:40px;"> '+
                '<div style="text-align: center; color: #002856;"><strong>Civil &amp; Env. Eng. (CEE)</strong></div>'+
                '<section class="center">'+
                    '<div class="table__wrapper">'+
                        '<table class="table" style="width: 100%;">'+
                            '<thead>'+
                                '<tr class="roomCEE">'+
                                    '<th scope="col" style="background-color: #efefef; color: #002856; max-width: 20px; text-align: center;">Room:</th>'+
                                '</tr>'+
                                // '<tr class="zoomCEE">'+
                                //     '<th scope="col" style="background-color: #efefef; max-width: 70px">'+
                                //         '<gg-icon class="gg-camera" scope="col" style="align-content: center;"></gg-icon>'+
                                //     '</th>'+
                                // '</tr>'+
                                '<tr class="trackCEE">'+
                                    '<th scope="col" style="background-color: #efefef; max-width: 70px">&nbsp;</th>'+
                                '</tr>'+
                            '</thead>'+
                            '<tbody class="classCEE">'+
                                '<tr>'+
                                '<th class="borderLess" style="background-color: #efefef;">&nbsp;</th>'+
                                    '<td data-header="Track 6">'+
                                        '<p style="color: #002856;"><b>Environment</b></p>'+
                                    '</td>'+
                                '</tr>'+
                            '</tbody>'+
                        '</table>'+
                    '</div>'+
                '</section>'+
            '</div>';
        $(".engslTable").append(html);
        for(let i = (0 + totalTrackForCAP); i < (totalTrackForCEE + totalTrackForCAP); i++){
            $(".roomCEE").append('<th class="roomt'+(i+1)+'" scope="col" style="background-color: #efefef; color: #002856; max-width: 150px; font-weight: normal; text-align: center;">&nbsp;</th>');
            $(".zoomCEE").append('<th class="zoomborder" scope="col">'+
                '<a class="zoom" id="zoomt'+(i+1)+'" scope="col" target="_blank" title="Zoom link activated 10 minutes before start!">'+
                    '<span>'+
                        '<strong style="text-decoration: none;">Zoom ' + (i+1) +  '</strong>'+
                    '</span>'+
                '</a>'+
            '</th>');
            $(".trackCEE").append('<th scope="col" style="background-color: #efefef; color: #002856; text-align: center; max-width: 150px">Track ' + (i+1) + '</th>');
        }
        let CEEhtml = "";
        for(let i = 0; i < totalOrderForCEE; i++){
            CEEhtml += '<tr>' +
                '<th class="borderLess" scope="row" style="background-color: #efefef; color: #002856;">'+
                    timestartForCEE +
                '</th>';
            for(let j = (0 + totalTrackForCAP); j < (totalTrackForCEE + totalTrackForCAP); j++){

                CEEhtml += '<td data-header="Track ' + (j+1) + '" id="hover' + (i+1) + (j+1) + '"><button class="ceer' + (i+1) + 't' + (j+1) + '" id="slot' + (i+1) + (j+1) + '" onclick="passvalue(\'slot' + (i+1) + (j+1) + '\')" style="color: #002856;"></button>'+
                '<p class="ceeorgr' + (i+1) + 't' + (j+1) + ' companyName">&nbsp;</p>'+
                '</td>';
            }
            CEEhtml += '</tr>';
            timestartForCEE = getTime(timestartForCEE, timePerSlotForCEE);
        }
        $(".classCEE").append(CEEhtml);
    }
    if (totalTrackForCSE > 0) {
        var html = '<div class= "span11" style= "margin-top:0px; padding: unset;">'+
            '<div style= "text-align: center; color: #002856;">'+
                '<strong>Sofware Engineering Capstone (CSE)</strong>'+
            '</div>'+
            '<section class="center">'+
                '<div class="table__wrapper">'+
                    '<table class="table" style="width: 100%;">'+
                        '<thead>'+
                            '<tr class="roomCSE">'+
                                '<th scope="col" style="background-color: #efefef; color: #002856; max-width: 100px; text-align: center;">Room:</th>'+
                            '</tr>'+
                            // '<tr class="zoomCSE">'+
                            //     '<th scope="col" style="background-color: #efefef; max-width: 100px">'+
                            //         '<gg-icon class="gg-camera" scope="col" style="align-content: center;"></gg-icon>'+
                            //     '</th>'+
                            // '</tr>'+
                            '<tr class="trackCSE">'+
                                '<th scope="col" style="background-color: #efefef; max-width: 100px">&nbsp;</th>'+
                            '</tr>'+
                        '</thead>'+
                        '<tbody class="classCSE">'+
                            '<tr>'+
                                '<th class="borderLess" style="background-color: #efefef;">&nbsp;</th>'+
                                '<td data-header="Track 1" style="color: #FFBF3C;">'+
                                    '<p style="color:#FFBF3C; font-weight: bolder;">'+
                                        '<b>Tim Berners-Lee</b>'+
                                    '</p>'+
                                '</td>'+
                                '<td data-header="Track 2" style="color: #FFBF3C;">'+
                                    '<p style="color:#FFBF3C; font-weight: bolder;">'+
                                        '<b>Grace Hopper</b>'+
                                    '</p>'+
                                '</td>'+
                                // '<td data-header="Track 3" style="color: #FFBF3C;">'+
                                //     '<p style="color:#FFBF3C; font-weight: bolder;">'+
                                //         '<b>John von Neumann</b>'+
                                //     '</p>'+
                                // '</td>'+
                            '</tr>'+
                        '</tbody>'+
                    '</table>'+
                '</div>'+
            '</section>'+
        '</div>';
        $(".cseTable").append(html);
        for(let i = (0 + totalTrackForCAP + totalTrackForCEE); i < (totalTrackForCSE + totalTrackForCAP + totalTrackForCEE); i++){
            $(".roomCSE").append('<th class="roomt'+(i+1)+'" scope="col" style="background-color: #efefef; color: #002856; font-weight: normal; text-align: center;">&nbsp;</th>');
            $(".zoomCSE").append('<th class="zoomborder" scope="col">'+
                '<a class="zoom" id="zoomt'+(i+1)+'" scope="col" target="_blank" title="Zoom link activated 10 minutes before start!">'+
                    '<span>'+
                        '<strong style="text-decoration: none;">Zoom ' + (i+1) + '</strong>'+
                    '</span>'+
                '</a>'+
            '</th>');
            $(".trackCSE").append('<th scope="col" style="background-color: #efefef; color: #002856; text-align: center;">Track ' + (i+1) + '</th>');
        }
        let CSEhtml = "";
        for(let i = 0; i < totalOrderForCSE; i++){
            CSEhtml += '<tr>' +
                '<th class="borderLess" scope="row" style="background-color: #efefef; color: #002856;">'+
                    timestartForCSE +
                '</th>';
            for(let j = (0 + totalTrackForCAP + totalTrackForCEE); j < (totalTrackForCSE + totalTrackForCAP + totalTrackForCEE); j++){

                CSEhtml += '<td data-header="Track ' + (j+1) + '" id="hover' + (i+1) + (j+1) + '"><button class="cser' + (i+1) + 't' + (j+1) + '" id="slot' + (i+1) + (j+1) + '" onclick="passvalue(\'slot' + (i+1) + (j+1) + '\')" style="color: #FFBF3C;"></button>'+
                '<p class="cseorgr' + (i+1) + 't' + (j+1) + ' companyNameC">&nbsp;</p>'+
                '</td>';
            }
            CSEhtml += '</tr>';
            timestartForCSE = getTime(timestartForCSE, timePerSlotForCSE);
        }
        $(".classCSE").append(CSEhtml);

    }

    // Pulls the room column from "2023-08-Fall-I2G-MASTER" spreadsheet.
    $.getJSON("https://sheets.googleapis.com/v4/spreadsheets/1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik/values/2025-I2G2-Tracks?alt=json&key=AIzaSyDWhIC7QQal9etKiwUDzs34yugQR0KqS94", function (data) {
        // Pull the class column from "2023-08-Fall-I2G-MASTER" spreadsheet.
        for (let i = 1; i <= totalRooms; i++) {
            $(".roomt" + i).prepend(data.values[i][1]); // there was a +1 here after i, but it was causing the room to be off by one
        }
        // Pulls the zoom column from "2023-08-Fall-I2G-MASTER" spreadsheet.
        // It will add href to make zoom button active if there is a link present in zoom spreadsheet column
        for (let i = 1; i <= totalRooms; i++) {
            if (data.values[i + 1][2] != "") {
                document.getElementById("zoomt" + i).href = data.values[i + 1][2];
            }
        }
    });
});

$(document).ready(function () {

    // Pulls data from "2025-I2G2-WEB" spreadsheet.
    // This populates the schedule of CAP, CSE, and CEE
    $.getJSON("https://sheets.googleapis.com/v4/spreadsheets/1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik/values/A1:Y76?alt=json&key=AIzaSyDWhIC7QQal9etKiwUDzs34yugQR0KqS94", function (data) {


      for (let i = 1; i < data.values.length; i++) {
            if (data.values[i][3] == "CAP") { // Set to CAP1 to handle all data that is CAP1 under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    $(".capr" + order + "t" + track).prepend(data.values[i][4]);
                    $(".caporgr" + order + "t" + track).prepend(data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            }
            else if (data.values[i][3] == "CSE") { // Set to CSE to handle all data that is CSE under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    $(".cser" + order + "t" + track).prepend(data.values[i][4]);
                    $(".cseorgr" + order + "t" + track).prepend(data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            }
            else if (data.values[i][3] == "CEE") { // Set to CEE to handle all data that is CEE under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    $(".ceer" + order + "t" + track).prepend(data.values[i][4]);
                    $(".ceeorgr" + order + "t" + track).prepend(data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            }
            else if (data.values[i][3] == "EngSL") { // Set to EngSL to handle all data that is EngSL under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    $(".engslr" + order + "t" + track).prepend(data.values[i][4]);
                    $(".engslorgr" + order + "t" + track).prepend(data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            }

            // If you want to add another class, just copy paste and mnake sure data.values[i][3] is == to whatever its named in the Class Column
            // If you want to add another row or track make sure it follows the same format as the others, i.e. button class=capr(order)t(track), id=slot(order)(track), passvalue=slot(order)(track), p class = caporgr(order)t(track) *(each row timeslot will have the same order number)*
            else {
                console.log("Error 01 occured");
            }
        }
    });
});
