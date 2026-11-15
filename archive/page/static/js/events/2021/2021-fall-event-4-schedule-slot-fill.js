$(document).ready(function () {
    $.getJSON("/api/sheets/1dZADXdBWnRw-EO-2pL3DuuNfFODqIzUflQ6yjyH_pUo/values/2021-01-Fall-I2G-WEB", function (data) {
        for (let i = 1; i < data.values.length; i++) {
            if (data.values[i][3] == "CAP") {
                let track = data.values[i][0];
                let order = data.values[i][1];
                prependSheetText(".capr" + order + "t" + track, data.values[i][4]);
                prependSheetText(".caporgr" + order + "t" + track, data.values[i][7]);
                document.getElementById("hover" + order + "" + track).title = data.values[i][11];
            } else if (data.values[i][3] == "CSE") {
                let track = data.values[i][0];
                let order = data.values[i][1];
                prependSheetText(".cser" + order + "t" + track, data.values[i][4]);
                prependSheetText(".cseorgr" + order + "t" + track, data.values[i][7]);
                document.getElementById("hover" + order + "" + track).title = data.values[i][11];
            } else if (data.values[i][3] == "CEE") {
                let track = data.values[i][0];
                let order = data.values[i][1];
                prependSheetText(".ceer" + order + "t" + track, data.values[i][4]);
                prependSheetText(".ceeorgr" + order + "t" + track, data.values[i][7]);
                document.getElementById("hover" + order + "" + track).title = data.values[i][11];
            } else {
                console.log("Error 01 occured");
            }
        }
    });
});
