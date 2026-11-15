        $(document).ready(function () {
            // Pulls the winner column from "2022-08-Fall-I2G-MASTER" spreadsheet.
            // .winnert1 means its the class for winner track 1. row x column 6 is the item in the winner column
            $.getJSON("/api/sheets/1VF29jHnlXbl02BK6_GPv91hADGM_QsvvM_SgH2X8Ohs/values/I2G-tracks", function (data) {
                prependSheetText(".winnert1", data.values[2][6]);
                prependSheetText(".winnert2", data.values[3][6]);
                prependSheetText(".winnert3", data.values[4][6]);
                prependSheetText(".winnert4", data.values[5][6]);
                prependSheetText(".winnert5", data.values[6][6]);
                prependSheetText(".winnert6", data.values[7][6]);
                prependSheetText(".winnert7", data.values[8][6]);
                prependSheetText(".winnert8", data.values[9][6]);
                prependSheetText(".winnert9", data.values[10][6]);

                prependSheetText(".trackname1", data.values[2][4]);
                prependSheetText(".trackname2", data.values[3][4]);
                prependSheetText(".trackname3", data.values[4][4]);
                prependSheetText(".trackname4", data.values[5][4]);
                prependSheetText(".trackname5", data.values[6][4]);
                prependSheetText(".trackname6", data.values[7][4]);
                prependSheetText(".trackname7", data.values[8][4]);
                prependSheetText(".trackname8", data.values[9][4]);
                prependSheetText(".trackname9", data.values[10][4]);

            });
        });
