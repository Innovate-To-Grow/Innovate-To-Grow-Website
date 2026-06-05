$(document).ready(function () {
    // Pulls the winner column from "2022-08-Fall-I2G-MASTER" spreadsheet.
    // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
    $.getJSON("/api/sheets/1L3fgZFAWnwXbRqn2Gt8Qf14-MCGxB46KZ3lfWe1a5ps/values/I2G-Tracks", function (data) {
        $(".winnert1").prepend(data.values[2][6]);
        $(".winnert2").prepend(data.values[3][6]);
        $(".winnert3").prepend(data.values[4][6]);
        $(".winnert4").prepend(data.values[5][6]);
        $(".winnert5").prepend(data.values[6][6]);
    });
});
