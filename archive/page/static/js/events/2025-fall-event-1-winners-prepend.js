$(document).ready(function () {
    // Pulls the winner column from "2022-08-Fall-I2G-MASTER" spreadsheet.
    // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
    $.getJSON("/api/sheets/1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik/values/2025-I2G2-Tracks", function (data) {
        // CAP Track 1: Row 1 (FoodTech)
        prependSheetText(".winnert1", data.values[1][6]);
        // CAP Track 2: Row 2 (Precision)
        prependSheetText(".winnert2", data.values[2][6]);
        // CEE Track 3: Row 3 (Environment)
        prependSheetText(".winnert4", data.values[3][6]);
        // CSE Track 4: Row 4 (Tim Berners-Lee)
        prependSheetText(".winnert5", data.values[4][6]);
        // CSE Track 5: Row 5 (Grace Hopper)
        prependSheetText(".winnert6", data.values[5][6]);
        // $(".winnert7").prepend(data.values[8][6]);
        // $(".winnert8").prepend(data.values[9][6]);
        // $(".winnert9").prepend(data.values[10][6]);

        // CAP Track 1: Row 1 (FoodTech)
        prependSheetText(".trackname1", data.values[1][4]);
        // CAP Track 2: Row 2 (Precision)
        prependSheetText(".trackname2", data.values[2][4]);
        // CEE Track 3: Row 3 (Environment)
        prependSheetText(".trackname4", data.values[3][4]);
        // CSE Track 4: Row 4 (Tim Berners-Lee)
        prependSheetText(".trackname5", data.values[4][4]);
        // CSE Track 5: Row 5 (Grace Hopper)
        prependSheetText(".trackname6", data.values[5][4]);
        // $(".trackname7").prepend(data.values[8][4]);
        // $(".trackname8").prepend(data.values[9][4]);
        // $(".trackname9").prepend(data.values[10][4]);

    });
});
