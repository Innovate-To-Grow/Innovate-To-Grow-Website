// mergeFunctions.js

/**
 * Display abstract and student names when clicking details button in Search Tables
 * @param {Object} d - Data row object 
 * @returns {string} HTML for expanded row content
 */
function format(d) {
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr><td>Abstract:</td><td>' + d["Abstract"] + '</td></tr>' +
        '<tr><td>Student Names:</td><td>' + d["Student Names"] + '</td></tr>' +
        '</table>';
}

/**
 * Display details with project URL for merged table rows
 * @param {Array} d - Data row array 
 * @returns {string} HTML for expanded row content
 */
function mergeformat(d) {
    // Generate a project UUID if it's not already in the data
    const projectUuid = d[11] || generateProjectUuid(d[0], d[1], d[2], d[4]); 
    
    // Create proper project URL
    const projectUrl = `/project/${projectUuid}`;
    const fullUrl = window.location.origin + projectUrl;
    
    return '<table cellpadding="5" cellspacing="0" border="0" style="padding-left:50px;">' +
        '<tr>' +
        '<td style="vertical-align: top;">Abstract:</td>' +
        '<td class="abstract-content" style="line-height: 1.5;">' + d[8] + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td style="vertical-align: top;">Student Names:</td>' +
        '<td class="student-names-content" style="line-height: 1.5;">' + d[9] + '</td>' +
        '</tr>' +
        '<tr>' +
        '<td style="vertical-align: middle;">Project URL:</td>' +
        '<td>' +
            '<span class="project-url" style="display: none;">' + projectUrl + '</span>' +
            '<a href="' + projectUrl + '" target="_blank" class="project-link" style="color: #0A3B80; text-decoration: underline; font-weight: 500; transition: color 0.2s ease, transform 0.2s ease; display: inline-block;"' + 
            ' onmouseover="this.style.color=\'#0062cc\'; this.style.transform=\'scale(1.02)\'" ' +
            ' onmouseout="this.style.color=\'#0A3B80\'; this.style.transform=\'scale(1)\'">' + 
            fullUrl + '</a>' +
        '</td>' +
        '</tr>' +
        '</table>';
}

/**
 * Generate a UUID from project data by hashing collection ID and project title
 * @param {string} yearSemester - Year and semester
 * @param {string} classCode - Class code
 * @param {string} teamNumber - Team number
 * @param {string} projectTitle - Project title
 * @returns {string} UUID for the project
 */
function generateProjectUuid(yearSemester, classCode, teamNumber, projectTitle) {
    // This function relies on currentCollectionId global variable
    // Get current collection ID if available, otherwise use a timestamp
    const collectionContext = window.currentCollectionId || ('temp_' + new Date().getTime());
    
    // Combine project title with collection context to create a unique string
    const baseString = `${collectionContext}-${projectTitle || yearSemester+classCode+teamNumber}`;
    
    // Create a simple hash from the string
    let hash = 0;
    for (let i = 0; i < baseString.length; i++) {
        const char = baseString.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32bit integer
    }
    
    // Convert to hex and ensure positive value
    const hexHash = Math.abs(hash).toString(16);
    
    // Add a prefix to make it clear this is a project ID
    return `proj-${hexHash}`;
}

/**
 * Save project to database
 * @param {Object} projectData - Project data
 * @returns {Promise} jQuery AJAX promise
 */
function saveProjectToDatabase(projectData) {
    return $.ajax({
        type: "POST",
        url: "/api/save-project", 
        data: JSON.stringify(projectData),
        contentType: "application/json; charset=utf-8",
        dataType: "json"
    });
}

/**
 * Generate a unique collection ID
 * @returns {string} Collection ID
 */
function generateCollectionId() {
    const timestamp = new Date().toISOString().split('T')[0].replace(/-/g, '');
    const random = Math.floor(Math.random() * 1000).toString().padStart(3, '0');
    return `curation_${timestamp}_${random}`;
}

/**
 * Create collection object from merged table data
 * @returns {Object} Collection data
 */
function createCollectionFromMergedTable() {
    // This function relies on merged_table, currentCollectionId, 
    // currentCollectionTitle, and currentCreatedAt global variables
    const tableData = window.merged_table.rows().data().toArray();
    
    // Create projects array
    const projects = tableData.map(row => {
        // Generate uuid if it doesn't exist
        const uuid = row[11] || generateProjectUuid(row[0], row[1], row[2], row[4]); 
        
        return {
            uuid: uuid,
            year_semester: row[0],
            class: row[1],
            team_number: row[2],
            team_name: row[3],
            project_title: row[4],
            organization: row[5],
            industry: row[6],
            abstract: row[8],
            student_names: row[9]
        };
    });
    
    // Use the existing collection ID if available, otherwise generate a new one
    const userId = window.userId;
    const collectionId = window.currentCollectionId || generateCollectionId();
    
    // Get the title from the input field if available, otherwise use default
    let title = $('#curation-title').length ? 
                $('#curation-title').val().trim() : 
                (window.currentCollectionTitle || "Curated Projects - " + new Date().toLocaleDateString());
    
    // If title is empty, use default
    if (!title) {
        title = "Curated Projects - " + new Date().toLocaleDateString();
    }
    
    // Save the current title
    window.currentCollectionTitle = title;
    
    // Always include createdAt field, but use existing time for updates
    const now = new Date().toISOString();
    
    // Get the editor content if it exists, otherwise use empty string
    const editorContent = $('#project-editor').length ? 
                          $('#project-editor').val() : 
                          ""; 
    

    return {
        _id: collectionId,
        userId: userId,
        title: title,
        projects: projects,
        editorContent: editorContent,
        createdAt: now,
    };
}

/**
 * Save collection to database
 * @param {Object} collection - Collection data
 * @returns {Promise} jQuery AJAX promise
 */
function saveCollectionToDatabase(collection) {
    return $.ajax({
        type: "POST", 
        url: "/api/save-collection",
        data: JSON.stringify(collection),
        contentType: "application/json; charset=utf-8",
        dataType: "json"
    });
}

/**
 * Update DataTable selection state
 * @param {Object} table - DataTable instance
 */
function updateDataTableSelectAllCtrl(table) {
    var $table = table.table().node();
    var $chkbox_all = $('tbody input[type="checkbox"]', $table);
    var $chkbox_checked = $('tbody input[type="checkbox"]:checked', $table);
    var chkbox_select_all = $('thead input[name="select_all"]', $table).get(0);

    // If none of the checkboxes are checked
    if ($chkbox_checked.length === 0) {
        chkbox_select_all.checked = false;
        if ('indeterminate' in chkbox_select_all) {
            chkbox_select_all.indeterminate = false;
        }
    // If all of the checkboxes are checked
    } else if ($chkbox_checked.length === $chkbox_all.length) {
        chkbox_select_all.checked = true;
        if ('indeterminate' in chkbox_select_all) {
            chkbox_select_all.indeterminate = false;
        }
    // If some of the checkboxes are checked
    } else {
        chkbox_select_all.checked = true;
        if ('indeterminate' in chkbox_select_all) {
            chkbox_select_all.indeterminate = true;
        }
    }
}

/**
 * Initialize share buttons behavior
 */
function initializeShareButtons() {
    if (window.location.pathname.includes('/past-projects/')) {
        $('.btn-share-url').each(function() {
            var $button = $(this);
            var currentUrl = window.location.href;
            
            $button
                .text('Copy URL')
                .off('click')
                .on('click', function() {
                    navigator.clipboard.writeText(currentUrl);
                    $(this).text('Copied!');
                    setTimeout(function() {
                        $(this).text('Copy URL');
                    }.bind(this), 2000);
                });
        });
    }
}

/**
 * Reset current collection state
 */
function resetCurrentCollection() {
    window.currentCollectionId = null;
    window.currentCollectionTitle = null;
    window.currentCreatedAt = null;
    $('.sharing').text('Save & Share Collection');
    
    // Reset title input if it exists
    if ($('#curation-title').length) {
        $('#curation-title').val('Curated Projects - ' + new Date().toLocaleDateString());
    }
}

/**
 * Format projects for editor display
 * @param {Array} rowsData - Array of row data
 * @returns {string} Formatted text for editor
 */
function formatProjectsForEditor(rowsData) {
    let formattedText = '';
    
    // Loop through each row
    for (let i = 0; i < rowsData.length; i++) {
        const row = rowsData[i];
        const projectUrl = window.location.origin + `/project/${row[11] || generateProjectUuid(row[0], row[1], row[2], row[4])}`;
        const projectTitle = row[4] || `Untitled Project ${i+1}`;
        
        // Format project data with project title as header
        formattedText += `${projectTitle}\n`;
        formattedText += `${'='.repeat(projectTitle.length)}\n`;
        formattedText += `Year-Semester: ${row[0]}\n`;
        formattedText += `Class: ${row[1]}\n`;
        formattedText += `Team #: ${row[2]}\n`;
        formattedText += `Team Name: ${row[3]}\n`;
        formattedText += `Organization: ${row[5]}\n`;
        formattedText += `Industry: ${row[6]}\n`;
        formattedText += `Abstract:\n${row[8]}\n\n`;
        formattedText += `Student Names:\n${row[9]}\n\n`;
        formattedText += `Project URL: ${projectUrl}\n\n`;
        
        // Add separator between projects
        if (i < rowsData.length - 1) {
            formattedText += `\n-------------------------------------------\n\n`;
        }
    }
    
    return formattedText;
}

// Add error handling for required globals
function checkRequiredGlobals() {
    const required = ['merged_table', 'currentCollectionId', 'currentCollectionTitle', 'currentCreatedAt'];
    const missing = required.filter(name => typeof window[name] === 'undefined');
    if (missing.length) {
        console.warn(`Missing required global variables: ${missing.join(', ')}`);
    }
}

// Add validation for data parameters
function validateProjectData(data) {
    const required = ['year_semester', 'class', 'team_number', 'project_title'];
    const missing = required.filter(field => !data[field]);
    if (missing.length) {
        throw new Error(`Missing required project fields: ${missing.join(', ')}`);
    }
}

// Export as global functions instead of ES6 modules
// since the main script doesn't use import statements
window.MergeFunctions = {
    format,
    mergeformat,
    generateProjectUuid,
    saveProjectToDatabase,
    generateCollectionId,
    createCollectionFromMergedTable,
    saveCollectionToDatabase,
    updateDataTableSelectAllCtrl,
    initializeShareButtons,
    resetCurrentCollection,
    formatProjectsForEditor,
    checkRequiredGlobals,
    validateProjectData
};
