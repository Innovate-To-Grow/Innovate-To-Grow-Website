function prependSheetText(selector, value) {
    $(selector).prepend(document.createTextNode(value == null ? "" : String(value)));
}

$(document).ready(function () {
    // Pulls the winner column from "2022-08-Fall-I2G-MASTER" spreadsheet.
    // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
    $.getJSON("/api/sheets/1L3fgZFAWnwXbRqn2Gt8Qf14-MCGxB46KZ3lfWe1a5ps/values/I2G-Tracks", function (data) {
        prependSheetText(".winnert1", data.values[2][6]);
        prependSheetText(".winnert2", data.values[3][6]);
        prependSheetText(".winnert3", data.values[4][6]);
        prependSheetText(".winnert4", data.values[5][6]);
        prependSheetText(".winnert5", data.values[6][6]);
    });
});
