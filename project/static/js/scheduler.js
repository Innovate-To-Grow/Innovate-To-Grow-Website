function escapeHtml(value) {
    return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function format(row) {
    var abstractText = escapeHtml(row.Abstract || "");
    var studentNames = escapeHtml(row["Student Names"] || "");

    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        "<tr>" +
        "<td>Abstract:</td>" +
        "<td>" + (abstractText || "&nbsp;") + "</td>" +
        "</tr>" +
        "<tr>" +
        "<td>Student Names:</td>" +
        "<td>" + (studentNames || "&nbsp;") + "</td>" +
        "</tr>" +
        "</table>";
}

function getTime(time, addMinutes) {
    var parts = String(time).split(":");
    var hours = parseInt(parts[0], 10);
    var minutes = parseInt(parts[1], 10) + parseInt(addMinutes, 10);

    if (minutes >= 60) {
        hours += Math.floor(minutes / 60);
        minutes = minutes % 60;
    }

    if (minutes < 10) {
        minutes = "0" + minutes;
    }

    if (hours > 12) {
        hours = hours - 12;
    }

    return hours + ":" + minutes;
}

function setStatusMessage(message, isError) {
    var status = $("#schedule-status");
    status.text(message);
    status.css("display", "block");
    status.css("color", isError ? "#b42318" : "#475467");
}

function clearStatusMessage() {
    $("#schedule-status").text("").css("display", "none");
}

function getInitialSearch() {
    return new URLSearchParams(window.location.search).get("value") || "";
}

function slotKey(track, order) {
    return String(track) + ":" + String(order);
}

var scheduleTable = null;

var sectionOrder = ["CAP", "CEE", "CSE"];
var sectionConfig = {
    "CAP": {
        "container": ".capTable",
        "wrapperClass": "span7",
        "wrapperStyle": "",
        "title": "Engineering Capstone (CAP)",
        "slotColor": "#002856",
        "topicColor": "#002856",
        "timeStart": "1:00",
        "timePerSlot": 30
    },
    "CEE": {
        "container": ".engslTable",
        "wrapperClass": "span4",
        "wrapperStyle": "margin-left:40px;",
        "title": "Civil & Env. Eng. (CEE)",
        "slotColor": "#002856",
        "topicColor": "#002856",
        "timeStart": "1:00",
        "timePerSlot": 30
    },
    "CSE": {
        "container": ".cseTable",
        "wrapperClass": "span11",
        "wrapperStyle": "margin-top:0px; padding: unset;",
        "title": "Software Engineering Capstone (CSE)",
        "slotColor": "#FFBF3C",
        "topicColor": "#FFBF3C",
        "timeStart": "1:00",
        "timePerSlot": 20
    }
};

function buildSlotMap(projects) {
    var slotMap = {};
    projects.forEach(function (project) {
        slotMap[slotKey(project.Track, project.Order)] = project;
    });
    return slotMap;
}

function getSectionTracks(allTracks, sectionClass) {
    return allTracks
        .filter(function (track) {
            return track.Class === sectionClass;
        })
        .sort(function (left, right) {
            return left.Track - right.Track;
        });
}

function getMaxOrderForSection(sectionTracks, projects) {
    var trackNumbers = {};
    var maxOrder = 0;

    sectionTracks.forEach(function (track) {
        trackNumbers[track.Track] = true;
    });

    projects.forEach(function (project) {
        if (trackNumbers[project.Track] && project.Order > maxOrder) {
            maxOrder = project.Order;
        }
    });

    return maxOrder;
}

function renderScheduleSlot(track, order, slotMap, config) {
    var slot = slotMap[slotKey(track.Track, order)];
    var titleAttribute = "";

    if (slot && slot.NameTitle) {
        titleAttribute = ' title="' + escapeHtml(slot.NameTitle) + '"';
    }

    if (!slot) {
        return '<td data-header="Track ' + track.Track + '"' + titleAttribute +
            ' style="color: #002856; background-color: rgb(247, 247, 247);">&nbsp;</td>';
    }

    if (slot.IsBreak) {
        return '<td data-header="Track ' + track.Track + '"' + titleAttribute +
            ' style="color: #002856; background-color: rgb(247, 247, 247);">' +
            '<p style="color: rgb(0, 40, 86); font-weight: bolder; text-align: center;">Break</p>' +
            "</td>";
    }

    var primaryLabel = escapeHtml(slot["Team#"] || slot.TeamName || slot["Project Title"] || "");
    var searchValue = escapeHtml(String(slot["Team#"] || slot.TeamName || slot["Project Title"] || ""));
    var organization = slot.Organization ? escapeHtml(slot.Organization) : "";
    var organizationMarkup = organization
        ? '<p style="color: #002856; margin-top: 4px;">' + organization + "</p>"
        : "";

    return '<td data-header="Track ' + track.Track + '"' + titleAttribute +
        ' style="color: #002856; background-color: rgb(247, 247, 247);">' +
        '<button type="button" class="schedule-team-link" data-search-value="' + searchValue +
        '" style="color: ' + config.slotColor + ';">' + primaryLabel + "</button>" +
        organizationMarkup +
        "</td>";
}

function renderSection(sectionClass, allTracks, projects, slotMap) {
    var config = sectionConfig[sectionClass];
    var container = $(config.container);
    var sectionTracks = getSectionTracks(allTracks, sectionClass);
    var maxOrder = getMaxOrderForSection(sectionTracks, projects);
    var currentTime = config.timeStart;
    var showTopicRow = sectionTracks.some(function (track) {
        return track.Topic;
    });
    var html = "";

    container.empty();

    if (!sectionTracks.length || !maxOrder) {
        return;
    }

    html += '<div class="' + config.wrapperClass + '"';
    if (config.wrapperStyle) {
        html += ' style="' + config.wrapperStyle + '"';
    }
    html += ">";
    html += '<div style="text-align: center; color: #002856;"><strong>' +
        escapeHtml(config.title) + "</strong></div>";
    html += '<section class="center"><div class="table__wrapper"><table class="table" style="width: 100%;">';
    html += "<thead>";
    html += '<tr><th scope="col" style="background-color: #efefef; color: #002856; text-align: center;">Room:</th>';
    sectionTracks.forEach(function (track) {
        html += '<th scope="col" style="background-color: #efefef; color: #002856; text-align: center; font-weight: normal;">' +
            (track.Room ? escapeHtml(track.Room) : "&nbsp;") + "</th>";
    });
    html += "</tr>";
    html += '<tr><th scope="col" style="background-color: #efefef;">&nbsp;</th>';
    sectionTracks.forEach(function (track) {
        html += '<th scope="col" style="background-color: #efefef; color: #002856; text-align: center;">Track ' +
            track.Track + "</th>";
    });
    html += "</tr>";
    html += "</thead>";
    html += "<tbody>";

    if (showTopicRow) {
        html += "<tr>";
        html += '<th class="borderLess" style="background-color: #efefef;">&nbsp;</th>';
        sectionTracks.forEach(function (track) {
            html += '<td data-header="Track ' + track.Track + '" style="color: #002856;">' +
                '<p style="color:' + config.topicColor + '; font-weight: bolder;">' +
                (track.Topic ? escapeHtml(track.Topic) : "&nbsp;") +
                "</p></td>";
        });
        html += "</tr>";
    }

    for (var order = 1; order <= maxOrder; order += 1) {
        html += "<tr>";
        html += '<th class="borderLess" scope="row" style="background-color: #efefef; color: #002856;">' +
            currentTime + "</th>";
        sectionTracks.forEach(function (track) {
            html += renderScheduleSlot(track, order, slotMap, config);
        });
        html += "</tr>";
        currentTime = getTime(currentTime, config.timePerSlot);
    }

    html += "</tbody></table></div></section></div>";
    container.append(html);
}

function renderSchedule(tracks, projects) {
    var slotMap = buildSlotMap(projects);

    sectionOrder.forEach(function (sectionClass) {
        renderSection(sectionClass, tracks, projects, slotMap);
    });
}

function renderProjectsTable(projects) {
    var searchableProjects = projects.filter(function (project) {
        return project["Team#"] || project.TeamName || project["Project Title"];
    });

    if ($.fn.DataTable.isDataTable("#example")) {
        $("#example").DataTable().clear().destroy();
    }

    scheduleTable = $("#example").DataTable({
        pageLength: 10,
        search: {
            search: getInitialSearch()
        },
        data: searchableProjects,
        columns: [
            {"data": "Order"},
            {"data": "Track"},
            {"data": "Year-Semester"},
            {"data": "Class"},
            {"data": "Team#"},
            {"data": "TeamName"},
            {"data": "Project Title"},
            {"data": "Organization"},
            {"data": "Industry"},
            {
                "className": "details-control",
                "orderable": false,
                "data": null,
                "defaultContent": ""
            },
            {
                "data": "Abstract",
                "bVisible": false
            },
            {
                "data": "Student Names",
                "bVisible": false
            }
        ],
        order: [
            [1, "asc"],
            [0, "asc"]
        ]
    });

    $("#example tbody")
        .off("click", "td.details-control")
        .on("click", "td.details-control", function () {
            var rowElement = $(this).closest("tr");
            var row = scheduleTable.row(rowElement);

            if (row.child.isShown()) {
                row.child.hide();
                rowElement.removeClass("shown");
                rowElement.css("color", "Black");
                rowElement.css("font-weight", "normal");
            } else {
                row.child(format(row.data())).show();
                rowElement.addClass("shown");
                rowElement.css("color", "#162D4F");
                rowElement.css("font-weight", "bold");
            }
        });
}

function passvalue(searchValue) {
    if (!scheduleTable) {
        return;
    }

    var params = new URLSearchParams(window.location.search);
    if (searchValue) {
        params.set("value", searchValue);
    } else {
        params.delete("value");
    }

    scheduleTable.search(searchValue || "").draw();

    var nextUrl = window.location.pathname;
    if (params.toString()) {
        nextUrl += "?" + params.toString();
    }
    nextUrl += "#projects";
    window.history.replaceState({}, "", nextUrl);

    var projectsTable = document.getElementById("projects");
    if (projectsTable) {
        projectsTable.scrollIntoView({behavior: "smooth", block: "start"});
    }
}

$(document).on("click", ".schedule-team-link", function () {
    passvalue(String($(this).data("searchValue") || ""));
});

$(document).ready(function () {
    $.getJSON("/api/schedule-data", function (payload) {
        var tracks = Array.isArray(payload.tracks) ? payload.tracks : [];
        var projects = Array.isArray(payload.projects) ? payload.projects : [];

        if (!tracks.length || !projects.length) {
            setStatusMessage("No schedule data is available yet.", false);
        } else {
            clearStatusMessage();
        }

        renderSchedule(tracks, projects);
        renderProjectsTable(projects);
    }).fail(function (jqXHR) {
        var errorMessage = "Schedule data is temporarily unavailable.";
        if (jqXHR.responseJSON && jqXHR.responseJSON.error) {
            errorMessage = jqXHR.responseJSON.error;
        }
        setStatusMessage(errorMessage, true);
    });
});
