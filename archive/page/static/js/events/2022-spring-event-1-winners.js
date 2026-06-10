$(document).ready(function () {
    // Pulls the winner column from "2022-01-Spring-I2G-MASTER" spreadsheet.
    // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
    $.getJSON("/api/sheets/1ByRYKwPkrD4edUVyd3hw3nTDY31ygyyx0QZOANF2vyc/values/I2G-Tracks", function (data) {
        prependSheetText(".winnert1", data.values[2][6]);
        prependSheetText(".winnert2", data.values[3][6]);
        prependSheetText(".winnert3", data.values[4][6]);
        prependSheetText(".winnert4", data.values[5][6]);
        prependSheetText(".winnert5", data.values[6][6]);
        prependSheetText(".winnert6", data.values[7][6]);
        prependSheetText(".winnert7", data.values[8][6]);
        prependSheetText(".winnert8", data.values[9][6]);
        prependSheetText(".winnert9", data.values[10][6]);
        prependSheetText(".winnert10", data.values[11][6]);
        prependSheetText(".winnert11", data.values[12][6]);
    });
});
