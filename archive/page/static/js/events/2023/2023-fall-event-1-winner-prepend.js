$(document).ready(function () {
    // Pulls the winner column from "2022-08-Fall-I2G-MASTER" spreadsheet.
    // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
    $.getJSON("/api/sheets/19VoMJrwiybqCNlepCa6QTBYIx5mqzZBVeOcPNxNvLnc/values/I2G-Tracks", function (data) {
        prependSheetText(".winnert1", data.values[2][6]);
        prependSheetText(".winnert2", data.values[3][6]);
        prependSheetText(".winnert3", data.values[4][6]);
        prependSheetText(".winnert4", data.values[5][6]);
        prependSheetText(".winnert5", data.values[6][6]);
        prependSheetText(".winnert6", data.values[7][6]);
        // $(".winnert7").prepend(data.values[8][6]);
        // $(".winnert8").prepend(data.values[9][6]);
        // $(".winnert9").prepend(data.values[10][6]);

        prependSheetText(".trackname1", data.values[2][4]);
        prependSheetText(".trackname2", data.values[3][4]);
        prependSheetText(".trackname3", data.values[4][4]);
        prependSheetText(".trackname4", data.values[5][4]);
        prependSheetText(".trackname5", data.values[6][4]);
        prependSheetText(".trackname6", data.values[7][4]);
        // $(".trackname7").prepend(data.values[8][4]);
        // $(".trackname8").prepend(data.values[9][4]);
        // $(".trackname9").prepend(data.values[10][4]);

    });
});
