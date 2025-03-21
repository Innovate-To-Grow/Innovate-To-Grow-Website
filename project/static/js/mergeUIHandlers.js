/**
 * Load data from Google Sheets and process it
 * @param {Array} team_names - Filter by team names
 * @param {Array} team_numbers - Filter by team numbers
 * @returns {Promise} Promise that resolves when data is loaded
 */
function loadDataFromGoogleSheets(team_names, team_numbers) {
    return new Promise((resolve, reject) => {
        $.getJSON("https://sheets.googleapis.com/v4/spreadsheets/1KATiK1Fnlb7Vsd186mCbaGjhID-OUGN-1QHWY8hIc5U/values/Past-Projects-WEB-LIVE?alt=json&key=***REMOVED_API_KEY***", function (data) {
            const processedData = [];
            const length = data.values.length;
            
            for (var i = 1; i < length; i++) {
                const subArray = data.values[i];
                // Clean up year-semester
                if (subArray[1] == "EngSL") {
                    subArray[0] = subArray[0].replace('-EngSL', '');
                } else if (subArray[1] == "CSE") {
                    subArray[0] = subArray[0].replace('-CSE', '');
                } else if (subArray[1] == "CAP") {
                    subArray[0] = subArray[0].replace('-CAP', '');
                } else if (subArray[1] == "CAP1") {
                    subArray[0] = subArray[0].replace('-CAP1', '');
                } else if (subArray[1] == "CEE") {
                    subArray[0] = subArray[0].replace('-CEE', '');
                }
                
                // Create data object
                const subdata = {
                    "Year-Semester": subArray[0],
                    "Class": subArray[1],
                    "Team#": subArray[2],
                    "Team Name": subArray[3],
                    "Project Title": subArray[4],
                    "Organization": subArray[5],
                    "Industry": subArray[6],
                    "Abstract": subArray[7],
                    "Student Names": subArray[8],
                };
                
                // Apply filters if needed
                if (team_names.length > 0 || team_numbers.length > 0) {
                    if (team_names.includes(subArray[3]) && team_numbers.includes(subArray[2])) {
                        processedData.push(subdata);
                    }
                } else {
                    processedData.push(subdata);
                }
            }
            
            resolve(processedData);
        }).fail(function(jqXHR, textStatus, errorThrown) {
            console.error("Error loading data:", textStatus, errorThrown);
            reject(errorThrown);
        });
    });
}

/**
 * Initialize title editing UI and handlers
 */
function initializeCurationTitle() {
    // Check if title container already exists
    if ($('#curation-title-container').length === 0) {
        // Create title container before the merged table
        const titleHtml = `
            <div id="curation-title-container" class="mb-3" style="margin-bottom: 15px;">
                <div class="d-flex align-items-center">
                    <input type="text" id="curation-title" 
                        class="form-control" 
                        value="${window.currentCollectionTitle || 'Curated Projects - ' + new Date().toLocaleDateString()}"
                        placeholder="Enter curation title..." 
                        style="font-size: 1.25rem; font-weight: 600; color: #162D4F; width: 100%; padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
                    <button id="save-title-btn" 
                        style="margin-left: 10px; background-color: #162D4F; color: #dbaa00; border: none; padding: 8px 12px; cursor: pointer; border-radius: 4px;">
                        <i class="fa fa-check"></i> Save
                    </button>
                </div>
                <small class="text-muted" style="display: block; margin-top: 5px; font-style: italic;">
                    Edit the curation title above. Changes will be saved when you update the collection.
                </small>
            </div>
        `;
        
        $('.mergeTable').prepend(titleHtml);
        
        // Add event handlers
        addTitleEventHandlers();
    } else {
        // If it already exists, just update value and reattach handlers
        $('#curation-title').val(window.currentCollectionTitle || 'Curated Projects - ' + new Date().toLocaleDateString());
        addTitleEventHandlers();
    }
}

/**
 * Add event handlers for title editing
 */
function addTitleEventHandlers() {
    // Remove existing handlers first to prevent duplicates
    $('#curation-title').off('input');
    $('#save-title-btn').off('click');
    
    // Add change handler for title field
    $('#curation-title').on('input', function() {
        window.titleChanged = true;
    });
    
    // Add click handler for save button
    $('#save-title-btn').on('click', function() {
        const newTitle = $('#curation-title').val().trim();
        if (newTitle) {
            window.currentCollectionTitle = newTitle;
            
            // Update text in sharing button if collection exists
            if (window.currentCollectionId) {
                $('.sharing').text('Update Collection');
            }
            
            // Show success message
            const $btn = $(this);
            $btn.html('<i class="fa fa-check"></i> Saved!');
            
            // Add visual feedback
            $btn.css({
                'background-color': '#28a745',
                'color': 'white'
            });
            
            setTimeout(() => {
                $btn.html('<i class="fa fa-check"></i> Save');
                $btn.css({
                    'background-color': '#162D4F',
                    'color': '#dbaa00'
                });
            }, 2000);
        }
    });
    
    // Add hover effects for better UX
    $('#save-title-btn').hover(
        function() { $(this).css('background-color', '#0e1d33'); },
        function() { $(this).css('background-color', '#162D4F'); }
    );
}

/**
 * Configure the merged table with DataTables
 * @returns {Object} DataTable instance
 */
function initializeMergedTable() {
    return $('.display').DataTable({
        "dom": 'lBfrtip',
        "language": { "emptyTable": "No entries have been saved yet." },
        "buttons": [
            'csv', 'excel', 'pdf',
            {
                "text": 'Save & Share Collection',
                "className": 'sharing',
                "action": saveOrUpdateCollection
            },
            {
                "text": 'Open in Editor',
                "className": 'open-editor-btn',
                "action": function() { openProjectEditor(); }
            },
            {
                "text": 'Show Details',
                "className": 'details-toggle-btn',
                "action": toggleAllDetails
            }
        ],
        "pageLength": 5,
        "lengthMenu": [[5, 10, 25, 100], [5, 10, 25, 100]],
        "search": { "search": document.location.search.replace(/^.*?\=/, '') },
        "aoColumns": getMergedTableColumns(),
        "order": [[1, 'asc']],
        "fixedHeader": { header: true, footer: true }
    });
}

/**
 * Get column definitions for merged table
 * @returns {Array} Array of column definitions
 */
function getMergedTableColumns() {
    return [
        {}, {}, {}, {}, {}, {}, {},
        {
            "className": 'details-control-merge',
            "orderable": false,
            "mDataProp": "null",
            "defaultContent": ''
        },
        { "bVisible": false }, // Abstract
        { "bVisible": false }, // Student Names
        {
            "data": null,
            "className": "dt-center editor-delete",
            "defaultContent": '<i class="fa fa-trash"/>',
            "orderable": false
        },
        { "bVisible": false, "data": null } // UUID column
    ];
}

/**
 * Toggle details for all rows in merged table
 */
function toggleAllDetails() {
    var $button = $('.details-toggle-btn');
    var isShowing = $button.text() === 'Hide Details';
    
    $('#example').find('td.details-control-merge').each(function() {
        var tr = $(this).closest('tr');
        var row = window.merged_table.row(tr);
        
        if (isShowing) {
            // Hide all details
            if (row.child.isShown()) {
                row.child.hide();
                tr.removeClass('shown');
                tr.css('color', 'Black');
                tr.css('font-weight', 'normal');
            }
        } else {
            // Show all details
            if (!row.child.isShown()) {
                row.child(mergeformat(row.data())).show();
                tr.addClass('shown');
                tr.css('color', '#162D4F');
                tr.css('font-weight', 'bold');
            }
        }
    });
    
    // Toggle button text
    $button.text(isShowing ? 'Show Details' : 'Hide Details');
}

/**
 * Save or update collection
 */
function saveOrUpdateCollection() {
    // Create a collection from the merged table
    const collection = createCollectionFromMergedTable();
    
    // Update button state to indicate saving in progress
    $('.sharing').text('Saving...').prop('disabled', true);
    
    // Save the collection to the database
    saveCollectionToDatabase(collection)
        .done(function(data) {
            // Store the collection ID for future updates
            window.currentCollectionId = collection._id;
            
            // Store the creation timestamp for future updates
            if (!window.currentCreatedAt && collection.createdAt) {
                window.currentCreatedAt = collection.createdAt;
            }
            
            // Open the collection page
            window.open(`/collection/${collection._id}`, "_blank");
            
            // Update button text to indicate we're now updating this collection
            setTimeout(function() {
                $('.sharing').text(window.currentCollectionId ? 'Update Collection' : 'Save & Share Collection').prop('disabled', false);
            }, 2000);
        })
        .fail(function(jqXHR, textStatus, errorThrown) {
            console.error("Error saving collection:", textStatus, errorThrown);
            $('.sharing').text('Error - Try Again').prop('disabled', false);
            
            // Reset button text after error
            setTimeout(function() {
                $('.sharing').text(window.currentCollectionId ? 'Update Collection' : 'Save & Share Collection');
            }, 3000);
        });
}

// Export as global object
window.MergeUIHandlers = {
    loadDataFromGoogleSheets,
    initializeCurationTitle,
    addTitleEventHandlers,
    initializeMergedTable,
    toggleAllDetails,
    saveOrUpdateCollection
};