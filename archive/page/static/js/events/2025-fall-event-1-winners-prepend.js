$(document).ready(function () {
    // Pulls the winner column from "2022-08-Fall-I2G-MASTER" spreadsheet.
    // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
    $.getJSON("/api/sheets/1o9xGjsaaS3BBOB4qLKVfRXWP0W-YDLa20TxPCEnRSik/values/2025-I2G2-Tracks", function (data) {
        // CAP Track 1: Row 1 (FoodTech)
        $(".winnert1").prepend(data.values[1][6]);
        // CAP Track 2: Row 2 (Precision)
        $(".winnert2").prepend(data.values[2][6]);
        // CEE Track 3: Row 3 (Environment)
        $(".winnert4").prepend(data.values[3][6]);
        // CSE Track 4: Row 4 (Tim Berners-Lee)
        $(".winnert5").prepend(data.values[4][6]);
        // CSE Track 5: Row 5 (Grace Hopper)
        $(".winnert6").prepend(data.values[5][6]);
        // $(".winnert7").prepend(data.values[8][6]);
        // $(".winnert8").prepend(data.values[9][6]);
        // $(".winnert9").prepend(data.values[10][6]);

        // CAP Track 1: Row 1 (FoodTech)
        $(".trackname1").prepend(data.values[1][4]);
        // CAP Track 2: Row 2 (Precision)
        $(".trackname2").prepend(data.values[2][4]);
        // CEE Track 3: Row 3 (Environment)
        $(".trackname4").prepend(data.values[3][4]);
        // CSE Track 4: Row 4 (Tim Berners-Lee)
        $(".trackname5").prepend(data.values[4][4]);
        // CSE Track 5: Row 5 (Grace Hopper)
        $(".trackname6").prepend(data.values[5][4]);
        // $(".trackname7").prepend(data.values[8][4]);
        // $(".trackname8").prepend(data.values[9][4]);
        // $(".trackname9").prepend(data.values[10][4]);

    });
});
