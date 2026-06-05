$(document).ready(function () {
    // Pulls the winner column from "2022-08-Fall-I2G-MASTER" spreadsheet.
    // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
    $.getJSON("/api/sheets/1MfFpZ0mn90UkqEuegBWopPqucfkmzzUWNl0oR2eSWdo/values/I2G-Tracks", function (data) {
        $(".winnert1").prepend(data.values[2][6]);
        $(".winnert2").prepend(data.values[3][6]);
        $(".winnert3").prepend(data.values[4][6]);
        $(".winnert4").prepend(data.values[5][6]);
        $(".winnert5").prepend(data.values[6][6]);
        $(".winnert6").prepend(data.values[7][6]);
        $(".winnert7").prepend(data.values[8][6]);
        $(".winnert8").prepend(data.values[9][6]);
        $(".winnert9").prepend(data.values[10][6]);

        $(".trackname1").prepend(data.values[2][4]);
        $(".trackname2").prepend(data.values[3][4]);
        $(".trackname3").prepend(data.values[4][4]);
        $(".trackname4").prepend(data.values[5][4]);
        $(".trackname5").prepend(data.values[6][4]);
        $(".trackname6").prepend(data.values[7][4]);
        $(".trackname7").prepend(data.values[8][4]);
        $(".trackname8").prepend(data.values[9][4]);
        $(".trackname9").prepend(data.values[10][4]);

    });
});
