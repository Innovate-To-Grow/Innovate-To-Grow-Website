$(document).ready(function() {
    var addCount = 1;            
    $("#addNewField").click(function() {
        var newInput = $("#flist");
        newInput.append(GetDynamicTextBox("", addCount));
        $("#flist").append(newInput);
        addCount += 1;
    });
});

function GetDynamicTextBox(value, addCount) {
    return '<div>' + 'Subdirectory&nbsp' + addCount + ':&nbsp' +
    '<input name = "subdir' + addCount + '"type="text" value = "' + value + '" />&nbsp;' +
    '<input type="button" value="Remove" class="remove" />' + '</div>' ;
}

$(function () {
    $("#addNewField").click(function() {
        $("#subDirList").append(GetDynamicTextBox("", addCount));                
         
    });
    
    $("body").on("click", ".remove", function () {
        $(this).closest("div").remove();
        addCount -= 1;
    });
});