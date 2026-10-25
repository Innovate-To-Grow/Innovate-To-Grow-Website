"""
CKEditor 5 configuration.

Used by CMS page blocks and any model field that uses ``CKEditor5Field``.
Only staff users may upload files through the editor.
"""

CKEDITOR_5_CONFIGS = {
    "default": {
        "toolbar": [
            "heading",
            "|",
            "bold",
            "italic",
            "underline",
            "strikethrough",
            "|",
            "bulletedList",
            "numberedList",
            "blockQuote",
            "|",
            "link",
            "insertImage",
            "mediaEmbed",
            "insertTable",
            "|",
            "sourceEditing",
        ],
        "image": {
            "toolbar": [
                "imageTextAlternative",
                "imageStyle:inline",
                "imageStyle:block",
                "imageStyle:side",
            ],
        },
        "table": {
            "contentToolbar": [
                "tableColumn",
                "tableRow",
                "mergeTableCells",
            ],
        },
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Paragraph", "class": "ck-heading_paragraph"},
                {"model": "heading2", "view": "h2", "title": "Heading 2", "class": "ck-heading_heading2"},
                {"model": "heading3", "view": "h3", "title": "Heading 3", "class": "ck-heading_heading3"},
                {"model": "heading4", "view": "h4", "title": "Heading 4", "class": "ck-heading_heading4"},
            ],
        },
    },
}

CKEDITOR_5_FILE_UPLOAD_PERMISSION = "staff"
