$(document).ready(function () {
    $.getJSON("/api/sheets/1WuiISEzbd0VCeB6F9cdR3dYFsZoFHwV6GWPH9iYYKQQ/values/I2G-Tracks", function (data) {
        $(".roomt1").prepend(data.values[2][1]);
        $(".roomt2").prepend(data.values[3][1]);
        $(".roomt3").prepend(data.values[4][1]);
        $(".roomt4").prepend(data.values[5][1]);
        $(".roomt5").prepend(data.values[6][1]);
        $(".roomt6").prepend(data.values[7][1]);
        $(".roomt7").prepend(data.values[8][1]);
        $(".roomt8").prepend(data.values[9][1]);
        $(".roomt9").prepend(data.values[10][1]);
        $(".roomt10").prepend(data.values[11][1]);
        $(".roomt11").prepend(data.values[12][1]);
        let counter = 1;
        for (let i = 2; i < 13; i++) {
            if (data.values[i][2] != "") {
                document.getElementById("zoomt" + counter).href = data.values[i][2];
            } else {
                // document.getElementById("zoomt"+counter).href = null;
            }
            counter++;
        }
    });
});
