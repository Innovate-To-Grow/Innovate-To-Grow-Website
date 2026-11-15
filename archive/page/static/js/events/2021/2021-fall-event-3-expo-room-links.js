$(document).ready(function () {
    $.getJSON("/api/sheets/1WuiISEzbd0VCeB6F9cdR3dYFsZoFHwV6GWPH9iYYKQQ/values/I2G-Tracks", function (data) {
        prependSheetText(".roomt1", data.values[2][1]);
        prependSheetText(".roomt2", data.values[3][1]);
        prependSheetText(".roomt3", data.values[4][1]);
        prependSheetText(".roomt4", data.values[5][1]);
        prependSheetText(".roomt5", data.values[6][1]);
        prependSheetText(".roomt6", data.values[7][1]);
        prependSheetText(".roomt7", data.values[8][1]);
        prependSheetText(".roomt8", data.values[9][1]);
        prependSheetText(".roomt9", data.values[10][1]);
        prependSheetText(".roomt10", data.values[11][1]);
        prependSheetText(".roomt11", data.values[12][1]);
        let counter = 1;
        for (let i = 2; i < 13; i++) {
            if (data.values[i][2] != "") {
                var zoomEl = document.getElementById("zoomt" + counter);
                var zoomUrl = safeSheetUrl(data.values[i][2]);
                if (zoomUrl) {
                    zoomEl.href = zoomUrl;
                    zoomEl.rel = "noopener noreferrer";
                }
            } else {
                // document.getElementById("zoomt"+counter).href = null;
            }
            counter++;
        }
    });
});
