import Foundation
import PDFKit
import PencilKit

@MainActor
final class LectureStore: ObservableObject {
    @Published var document: PDFDocument?
    @Published var fileURL: URL?
    @Published var currentPage: Int = 0
    @Published var notes: [Int: String] = [:]

    private var drawingCache: [Int: PKDrawing] = [:]
    private let fm = FileManager.default

    var pageCount: Int { document?.pageCount ?? 0 }
    var fileName: String { fileURL?.lastPathComponent ?? "" }

    func importPDF(from pickedURL: URL) throws {
        let accessed = pickedURL.startAccessingSecurityScopedResource()
        defer { if accessed { pickedURL.stopAccessingSecurityScopedResource() } }

        let docs = fm.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let appDir = docs.appendingPathComponent("LectureHelper", isDirectory: true)
        try fm.createDirectory(at: appDir, withIntermediateDirectories: true)

        var destination = appDir.appendingPathComponent(pickedURL.lastPathComponent)
        if fm.fileExists(atPath: destination.path) {
            let base = pickedURL.deletingPathExtension().lastPathComponent
            let ext = pickedURL.pathExtension
            destination = appDir.appendingPathComponent("\(base)-\(Int(Date().timeIntervalSince1970)).\(ext)")
        }
        try fm.copyItem(at: pickedURL, to: destination)

        guard let pdf = PDFDocument(url: destination) else {
            throw CocoaError(.fileReadCorruptFile)
        }

        document = pdf
        fileURL = destination
        currentPage = 0
        drawingCache.removeAll()
        loadNotes()
        objectWillChange.send()
    }

    func goPrevious() {
        guard currentPage > 0 else { return }
        currentPage -= 1
    }

    func goNext() {
        guard currentPage + 1 < pageCount else { return }
        currentPage += 1
    }

    func setPage(_ page: Int) {
        guard pageCount > 0 else { return }
        currentPage = min(max(page, 0), pageCount - 1)
    }

    func noteBindingText(for page: Int) -> String {
        notes[page] ?? ""
    }

    func setNote(_ text: String, for page: Int) {
        notes[page] = text
        saveNotes()
    }

    func appendTag(_ tag: String, to page: Int) {
        var text = notes[page] ?? ""
        if !text.isEmpty && !text.hasSuffix("\n") { text += "\n" }
        text += tag
        notes[page] = text
        saveNotes()
    }

    func drawing(for page: Int) -> PKDrawing {
        if let cached = drawingCache[page] { return cached }
        let url = drawingURL(page)
        if let data = try? Data(contentsOf: url),
           let drawing = try? PKDrawing(data: data) {
            drawingCache[page] = drawing
            return drawing
        }
        let empty = PKDrawing()
        drawingCache[page] = empty
        return empty
    }

    func saveDrawing(_ drawing: PKDrawing, for page: Int) {
        drawingCache[page] = drawing
        do {
            try fm.createDirectory(at: projectSupportDirectory(), withIntermediateDirectories: true)
            try drawing.dataRepresentation().write(to: drawingURL(page), options: .atomic)
        } catch {
            print("Drawing save error:", error)
        }
    }

    private func projectKey() -> String {
        let raw = fileURL?.deletingPathExtension().lastPathComponent ?? "untitled"
        let allowed = raw.map { ch -> Character in
            if ch.isLetter || ch.isNumber || ch == "-" || ch == "_" { return ch }
            return "_"
        }
        return String(allowed)
    }

    private func projectSupportDirectory() -> URL {
        let base = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        return base.appendingPathComponent("LectureHelperV3", isDirectory: true)
            .appendingPathComponent(projectKey(), isDirectory: true)
    }

    private func drawingURL(_ page: Int) -> URL {
        projectSupportDirectory().appendingPathComponent("page-\(page + 1).drawing")
    }

    private func notesURL() -> URL {
        projectSupportDirectory().appendingPathComponent("notes.json")
    }

    private func saveNotes() {
        do {
            try fm.createDirectory(at: projectSupportDirectory(), withIntermediateDirectories: true)
            let serializable = Dictionary(uniqueKeysWithValues: notes.map { (String($0.key), $0.value) })
            let data = try JSONEncoder().encode(serializable)
            try data.write(to: notesURL(), options: .atomic)
        } catch {
            print("Note save error:", error)
        }
    }

    private func loadNotes() {
        notes = [:]
        guard let data = try? Data(contentsOf: notesURL()),
              let decoded = try? JSONDecoder().decode([String: String].self, from: data) else { return }
        notes = Dictionary(uniqueKeysWithValues: decoded.compactMap { key, value in
            guard let index = Int(key) else { return nil }
            return (index, value)
        })
    }
}
