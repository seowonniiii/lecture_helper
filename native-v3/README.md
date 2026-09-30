# Lecture Helper V3 — iPad Native Prototype

This folder contains the first native iPad prototype built with SwiftUI + PDFKit + PencilKit.

## Current goals

- Open a lecture PDF from Files.
- Show page navigation at the top.
- Show the source file name under the lecture page.
- Switch the comment panel between right and bottom layouts.
- Apple Pencil draws through PencilKit only.
- Fingers pan and pinch-zoom the lecture page.
- Use the native PencilKit tool picker (pen, highlighter, eraser, colors).
- Save handwriting per original PDF page.
- Save text comments per original PDF page.
- Keep [시험], [중요], [교수설명], [질문] quick tags.

## Run directly on iPad with Swift Playground

1. Install **Swift Playground** from the App Store.
2. Open Swift Playground and create **New Playground → App**.
3. In the project sidebar, replace the starter app file with the contents of `LectureHelperV3App.swift`.
4. Replace the starter `ContentView.swift` with this folder's `ContentView.swift`.
5. Add two new Swift files:
   - `LectureStore.swift`
   - `PDFPencilCanvas.swift`
6. Run the app preview.
7. Tap **PDF 열기**, choose a lecture PDF from Files, and test with Apple Pencil.

Important: keep only one `@main` App type. If the starter project already contains `@main struct MyApp`, replace that file instead of adding a second app entry.

## Interaction model

- **Apple Pencil**: handwriting only.
- **One finger**: pan/scroll.
- **Two fingers / pinch**: zoom.
- Native `PKToolPicker`: Apple Pencil tool palette.

The key PencilKit setting is:

```swift
canvasView.drawingPolicy = .pencilOnly
```

The parent scroll view accepts direct finger touches only, while the PencilKit drawing gesture accepts Pencil touches only.

## Storage

When a PDF is imported, the app copies it into its own Documents/LectureHelper folder.

Per-page handwriting is saved as PencilKit `PKDrawing` data under Application Support. Page notes are saved as JSON. The current prototype therefore preserves handwriting and comments independently for each original PDF page.

## Next V3 milestones

1. Test Pencil feel and palm rejection on the real iPad.
2. Add left/right edge tap page turning without interfering with Pencil.
3. Add PDF export with handwriting flattened onto each page.
4. Add Markdown export using exact `<<<PAGE n>>>` markers.
5. Add DOCX export or a share sheet workflow.
6. Add project library / recent lectures.
7. Add optional audio recording + page/time markers.

## Source files

- `LectureHelperV3App.swift` — app entry.
- `ContentView.swift` — native iPad UI.
- `LectureStore.swift` — PDF, note, and drawing persistence.
- `PDFPencilCanvas.swift` — PDF page rendering + PencilKit + finger pan/zoom.
