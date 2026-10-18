/*
 * Searchable PDF text extraction for fonts without /ToUnicode mappings.
 * MuPDF.js: AGPL-3.0-or-later (https://mupdf.com/licensing/).
 * Processing stays on the user's device; PDFs are not uploaded.
 */
import {renderColoredWalk} from './color_text.js';

const MUPDF_DIST = 'https://cdn.jsdelivr.net/npm/mupdf@1.28.1/dist/';
let modulePromise;

async function loadMuPDF() {
  if (!modulePromise) {
    // Configure Emscripten's companion WASM URL before importing the module.
    globalThis.$libmupdf_wasm_Module = {
      locateFile: file => `${MUPDF_DIST}${file}`
    };
    modulePromise = import(`${MUPDF_DIST}mupdf.js`).catch(error => {
      modulePromise = null;
      throw error;
    });
  }
  return modulePromise;
}

export async function openTextReader(pdfBytes, expectedPages) {
  const mupdf = await loadMuPDF();
  const document = mupdf.Document.openDocument(pdfBytes, 'application/pdf');
  const count = document.countPages();
  if (count !== expectedPages) {
    document.destroy();
    throw new Error(`페이지 수 불일치: PDF.js ${expectedPages}p / MuPDF ${count}p`);
  }

  return {
    readPage(pageNumber, preserveWhitespace = true) {
      const page = document.loadPage(pageNumber - 1);
      let structured;
      try {
        structured = page.toStructuredText(preserveWhitespace ? 'preserve-whitespace' : '');
        return structured.asText();
      } finally {
        structured?.destroy();
        page.destroy();
      }
    },
    readPageRich(pageNumber, preserveWhitespace = true) {
      const page = document.loadPage(pageNumber - 1);
      let structured;
      try {
        const options = preserveWhitespace ? 'preserve-whitespace,preserve-spans' : 'preserve-spans';
        structured = page.toStructuredText(options);
        const plain = structured.asText();
        return { plain, ...renderColoredWalk(structured, plain) };
      } finally {
        structured?.destroy();
        page.destroy();
      }
    },
    close() {
      document.destroy();
    }
  };
}
