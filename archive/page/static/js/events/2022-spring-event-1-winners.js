$(document).ready(function () {
    // Pulls the winner column from "2022-01-Spring-I2G-MASTER" spreadsheet.
    // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
    $.getJSON("/api/sheets/1ByRYKwPkrD4edUVyd3hw3nTDY31ygyyx0QZOANF2vyc/values/I2G-Tracks", function (data) {
        $(".winnert1").prepend(data.values[2][6]);
        $(".winnert2").prepend(data.values[3][6]);
        $(".winnert3").prepend(data.values[4][6]);
        $(".winnert4").prepend(data.values[5][6]);
        $(".winnert5").prepend(data.values[6][6]);
        $(".winnert6").prepend(data.values[7][6]);
        $(".winnert7").prepend(data.values[8][6]);
        $(".winnert8").prepend(data.values[9][6]);
        $(".winnert9").prepend(data.values[10][6]);
        $(".winnert10").prepend(data.values[11][6]);
        $(".winnert11").prepend(data.values[12][6]);
    });
});
