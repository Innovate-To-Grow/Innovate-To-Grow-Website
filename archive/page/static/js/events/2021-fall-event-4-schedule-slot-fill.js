$(document).ready(function () {
    $.getJSON("/api/sheets/1dZADXdBWnRw-EO-2pL3DuuNfFODqIzUflQ6yjyH_pUo/values/2021-01-Fall-I2G-WEB", function (data) {
        for (let i = 1; i < data.values.length; i++) {
            if (data.values[i][3] == "CAP") {
                let track = data.values[i][0];
                let order = data.values[i][1];
                $(".capr" + order + "t" + track).prepend(data.values[i][4]);
                $(".caporgr" + order + "t" + track).prepend(data.values[i][7]);
                document.getElementById("hover" + order + "" + track).title = data.values[i][11];
            } else if (data.values[i][3] == "CSE") {
                let track = data.values[i][0];
                let order = data.values[i][1];
                $(".cser" + order + "t" + track).prepend(data.values[i][4]);
                $(".cseorgr" + order + "t" + track).prepend(data.values[i][7]);
                document.getElementById("hover" + order + "" + track).title = data.values[i][11];
            } else if (data.values[i][3] == "CEE") {
                let track = data.values[i][0];
                let order = data.values[i][1];
                $(".ceer" + order + "t" + track).prepend(data.values[i][4]);
                $(".ceeorgr" + order + "t" + track).prepend(data.values[i][7]);
                document.getElementById("hover" + order + "" + track).title = data.values[i][11];
            } else {
                console.log("Error 01 occured");
            }
        }
    });
});
