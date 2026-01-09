/**
 * Export utilities for past projects data.
 * Supports CSV, Excel, PDF, and print functionality.
 */

import * as XLSX from 'xlsx';
import jsPDF from 'jspdf';
import autoTable from 'jspdf-autotable';
import { saveAs } from 'file-saver';
import type { PastProject } from '../services/api';

/**
 * Generate a filename with current date.
 */
function generateFilename(extension: string): string {
  const date = new Date();
  const dateStr = date.toISOString().split('T')[0]; // YYYY-MM-DD
  return `i2g-past-projects-${dateStr}.${extension}`;
}

/**
 * Export projects data to CSV format.
 */
export function exportToCSV(projects: PastProject[], filename?: string): void {
  if (projects.length === 0) {
    alert('No data to export.');
    return;
  }

  // Create CSV header
  const headers = [
    'Year-Semester',
    'Class',
    'Team#',
    'Team Name',
    'Project Title',
    'Organization',
    'Industry',
    'Abstract',
    'Student Names',
  ];

  // Create CSV rows
  const rows = projects.map((project) => [
    project['Year-Semester'] || '',
    project['Class'] || '',
    project['Team#'] || '',
    project['Team Name'] || '',
    project['Project Title'] || '',
    project['Organization'] || '',
    project['Industry'] || '',
    project['Abstract'] || '',
    project['Student Names'] || '',
  ]);

  // Combine headers and rows
  const csvContent = [headers, ...rows]
    .map((row) =>
      row
        .map((cell) => {
          // Escape quotes and wrap in quotes if contains comma, newline, or quote
          const cellStr = String(cell || '');
          if (cellStr.includes(',') || cellStr.includes('\n') || cellStr.includes('"')) {
            return `"${cellStr.replace(/"/g, '""')}"`;
          }
          return cellStr;
        })
        .join(',')
    )
    .join('\n');

  // Add BOM for UTF-8 encoding
  const BOM = '\uFEFF';
  const blob = new Blob([BOM + csvContent], { type: 'text/csv;charset=utf-8;' });
  saveAs(blob, filename || generateFilename('csv'));
}

/**
 * Export projects data to Excel format.
 */
export function exportToExcel(projects: PastProject[], filename?: string): void {
  if (projects.length === 0) {
    alert('No data to export.');
    return;
  }

  // Prepare data for Excel
  const worksheetData = projects.map((project) => ({
    'Year-Semester': project['Year-Semester'] || '',
    'Class': project['Class'] || '',
    'Team#': project['Team#'] || '',
    'Team Name': project['Team Name'] || '',
    'Project Title': project['Project Title'] || '',
    'Organization': project['Organization'] || '',
    'Industry': project['Industry'] || '',
    'Abstract': project['Abstract'] || '',
    'Student Names': project['Student Names'] || '',
  }));

  // Create workbook and worksheet
  const workbook = XLSX.utils.book_new();
  const worksheet = XLSX.utils.json_to_sheet(worksheetData);

  // Set column widths
  worksheet['!cols'] = [
    { wch: 15 }, // Year-Semester
    { wch: 20 }, // Class
    { wch: 10 }, // Team#
    { wch: 25 }, // Team Name
    { wch: 40 }, // Project Title
    { wch: 25 }, // Organization
    { wch: 20 }, // Industry
    { wch: 50 }, // Abstract
    { wch: 30 }, // Student Names
  ];

  // Add worksheet to workbook
  XLSX.utils.book_append_sheet(workbook, worksheet, 'Past Projects');

  // Generate Excel file
  XLSX.writeFile(workbook, filename || generateFilename('xlsx'));
}

/**
 * Export projects data to PDF format.
 */
export function exportToPDF(projects: PastProject[], filename?: string): void {
  if (projects.length === 0) {
    alert('No data to export.');
    return;
  }

  const doc = new jsPDF('l', 'mm', 'a4'); // Landscape orientation

  // Add title
  doc.setFontSize(16);
  doc.text('I2G Past Projects', 14, 15);

  // Prepare table data
  const tableData = projects.map((project) => [
    project['Year-Semester'] || '',
    project['Class'] || '',
    project['Team#'] || '',
    project['Team Name'] || '',
    project['Project Title'] || '',
    project['Organization'] || '',
    project['Industry'] || '',
    project['Abstract'] || '',
    project['Student Names'] || '',
  ]);

  // Add table
  autoTable(doc, {
    head: [
      [
        'Year-Semester',
        'Class',
        'Team#',
        'Team Name',
        'Project Title',
        'Organization',
        'Industry',
        'Abstract',
        'Student Names',
      ],
    ],
    body: tableData,
    startY: 25,
    styles: { fontSize: 8, cellPadding: 2 },
    headStyles: { fillColor: [66, 139, 202], textColor: 255 },
    alternateRowStyles: { fillColor: [245, 245, 245] },
    margin: { top: 25, right: 14, bottom: 14, left: 14 },
    tableWidth: 'wrap',
  });

  // Save PDF
  doc.save(filename || generateFilename('pdf'));
}

/**
 * Print projects data in a print-friendly format.
 */
export function printTable(projects: PastProject[]): void {
  if (projects.length === 0) {
    alert('No data to print.');
    return;
  }

  // Create a print-friendly HTML table
  const printWindow = window.open('', '_blank');
  if (!printWindow) {
    alert('Please allow popups to print.');
    return;
  }

  const html = `
    <!DOCTYPE html>
    <html>
      <head>
        <title>I2G Past Projects</title>
        <style>
          @media print {
            @page {
              margin: 1cm;
            }
            body {
              margin: 0;
              padding: 0;
            }
          }
          body {
            font-family: Arial, sans-serif;
            font-size: 12px;
            padding: 20px;
          }
          h1 {
            margin-bottom: 20px;
            font-size: 18px;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
          }
          th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: left;
          }
          th {
            background-color: #428bca;
            color: white;
            font-weight: bold;
          }
          tr:nth-child(even) {
            background-color: #f5f5f5;
          }
          .abstract-cell, .names-cell {
            max-width: 300px;
            word-wrap: break-word;
          }
        </style>
      </head>
      <body>
        <h1>I2G Past Projects</h1>
        <table>
          <thead>
            <tr>
              <th>Year-Semester</th>
              <th>Class</th>
              <th>Team#</th>
              <th>Team Name</th>
              <th>Project Title</th>
              <th>Organization</th>
              <th>Industry</th>
              <th class="abstract-cell">Abstract</th>
              <th class="names-cell">Student Names</th>
            </tr>
          </thead>
          <tbody>
            ${projects
              .map(
                (project) => `
              <tr>
                <td>${escapeHtml(project['Year-Semester'] || '')}</td>
                <td>${escapeHtml(project['Class'] || '')}</td>
                <td>${escapeHtml(project['Team#'] || '')}</td>
                <td>${escapeHtml(project['Team Name'] || '')}</td>
                <td>${escapeHtml(project['Project Title'] || '')}</td>
                <td>${escapeHtml(project['Organization'] || '')}</td>
                <td>${escapeHtml(project['Industry'] || '')}</td>
                <td class="abstract-cell">${escapeHtml(project['Abstract'] || '')}</td>
                <td class="names-cell">${escapeHtml(project['Student Names'] || '')}</td>
              </tr>
            `
              )
              .join('')}
          </tbody>
        </table>
        <script>
          window.onload = function() {
            window.print();
          };
        </script>
      </body>
    </html>
  `;

  printWindow.document.write(html);
  printWindow.document.close();
}

/**
 * Escape HTML special characters.
 */
function escapeHtml(text: string): string {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}


