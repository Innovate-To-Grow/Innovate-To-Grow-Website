$(document).ready(function () {
    // Pulls the room column from "2022-01-Spring-I2G-MASTER" spreadsheet.
    $.getJSON("/api/sheets/1ByRYKwPkrD4edUVyd3hw3nTDY31ygyyx0QZOANF2vyc/values/I2G-Tracks", function (data) {
        $(".roomt1").prepend(data.values[2][1]);
        $(".roomt2").prepend(data.values[3][1]);
        $(".roomt3").prepend(data.values[4][1]);
        $(".roomt4").prepend(data.values[5][1]);
        $(".roomt5").prepend(data.values[6][1]);
        // $(".roomt6").prepend(data.values[7][1]); (this is commented out since track 6 and 7 share the same room)
        $(".roomt7").prepend(data.values[8][1]);
        $(".roomt8").prepend(data.values[9][1]);
        $(".roomt9").prepend(data.values[10][1]);
        $(".roomt10").prepend(data.values[11][1]);
        $(".roomt11").prepend(data.values[12][1]);
        let counter = 1;
        // Pulls the zoom column from "2022-01-Spring-I2G-MASTER" spreadsheet.
        // It will automatically make zoom button active if there is a link present in zoom spreadsheet column
        for (let i = 2; i < 13; i++) {
            if (data.values[i][2] != "" && i != 7) {
                document.getElementById("zoomt" + counter).href = data.values[i][2];
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
                    $(".capr" + order + "t" + track).prepend(data.values[i][4]);
                    $(".caporgr" + order + "t" + track).prepend(data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            } else if (data.values[i][3] == "CSE") { // Set to CSE to handle all data that is CSE under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    $(".cser" + order + "t" + track).prepend(data.values[i][4]);
                    $(".cseorgr" + order + "t" + track).prepend(data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            } else if (data.values[i][3] == "CEE") { // Set to CEE to handle all data that is CEE under Class Column in the spreadsheet
                let track = data.values[i][0];
                let order = data.values[i][1];
                if (track != "" && order != "") {
                    $(".ceer" + order + "t" + track).prepend(data.values[i][4]);
                    $(".ceeorgr" + order + "t" + track).prepend(data.values[i][7]);
                    document.getElementById("hover" + order + "" + track).title = data.values[i][11];
                }
            } else if (data.values[i][3] == "EngSL") { // Set to EngSL to handle all data that is EngSL under Class Column in the spreadsheet
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
