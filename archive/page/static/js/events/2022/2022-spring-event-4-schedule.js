$(document).ready(function () {
    // Pulls the room column from "2022-01-Spring-I2G-MASTER" spreadsheet.
    $.getJSON("/api/sheets/1ByRYKwPkrD4edUVyd3hw3nTDY31ygyyx0QZOANF2vyc/values/I2G-Tracks", function (data) {
        prependSheetText(".roomt1", data.values[2][1]);
        prependSheetText(".roomt2", data.values[3][1]);
        prependSheetText(".roomt3", data.values[4][1]);
        prependSheetText(".roomt4", data.values[5][1]);
        prependSheetText(".roomt5", data.values[6][1]);
        // $(".roomt6").prepend(data.values[7][1]); (this is commented out since track 6 and 7 share the same room)
        prependSheetText(".roomt7", data.values[8][1]);
        prependSheetText(".roomt8", data.values[9][1]);
        prependSheetText(".roomt9", data.values[10][1]);
        prependSheetText(".roomt10", data.values[11][1]);
        prependSheetText(".roomt11", data.values[12][1]);
        let counter = 1;
        // Pulls the zoom column from "2022-01-Spring-I2G-MASTER" spreadsheet.
        // It will automatically make zoom button active if there is a link present in zoom spreadsheet column
        for (let i = 2; i < 13; i++) {
            if (data.values[i][2] != "" && i != 7) {
                var zoomEl = document.getElementById("zoomt" + counter);
                var zoomUrl = safeSheetUrl(data.values[i][2]);
                if (zoomUrl) {
                    zoomEl.href = zoomUrl;
                    zoomEl.rel = "noopener noreferrer";
                }
            }
            counter++;
        }
    });
});

$(document).ready(function () {
    // Pulls data from "2022-01-Spring-I2G-WEB" spreadsheet.
    $.getJSON("/api/sheets/13Yds-sPSPjLSWYyCyIaHauTZ3lchGiNH1n-II6tJOMM/values/2022-01-Spring-I2G-WEB", function (data) {
        for (let i = 1; i < data.values.length; i++) {
            if ((data.values[i][3] == "CAP1") || (data.values[i][3] == "CAP")) { // Set to CAP1 to handle all data that is CAP1 under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    prependSheetText(".capr" + order + "t" + track, data.values[i][4]);
                    prependSheetText(".caporgr" + order + "t" + track, data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            } else if (data.values[i][3] == "CSE") { // Set to CSE to handle all data that is CSE under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    prependSheetText(".cser" + order + "t" + track, data.values[i][4]);
                    prependSheetText(".cseorgr" + order + "t" + track, data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            } else if (data.values[i][3] == "CEE") { // Set to CEE to handle all data that is CEE under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    prependSheetText(".ceer" + order + "t" + track, data.values[i][4]);
                    prependSheetText(".ceeorgr" + order + "t" + track, data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            } else if (data.values[i][3] == "EngSL") { // Set to EngSL to handle all data that is EngSL under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    prependSheetText(".engslr" + order + "t" + track, data.values[i][4]);
                    prependSheetText(".engslorgr" + order + "t" + track, data.values[i][7]);
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
