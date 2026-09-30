import SwiftUI
import Foundation
import UniformTypeIdentifiers
import UIKit
import PDFKit
import PencilKit

extension Notification.Name {
    static let lectureHelperPencilBegan = Notification.Name("LectureHelperPencilBegan")
}

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
        return String(raw.map { ch in
            (ch.isLetter || ch.isNumber || ch == "-" || ch == "_") ? ch : "_"
        })
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

struct PDFPencilCanvas: UIViewRepresentable {
    @ObservedObject var store: LectureStore
    var noteEditing: Bool

    func makeUIView(context: Context) -> PDFInkPageView {
        PDFInkPageView()
    }

    func updateUIView(_ uiView: PDFInkPageView, context: Context) {
        uiView.setNoteEditing(noteEditing)

        guard let document = store.document,
              store.currentPage >= 0,
              store.currentPage < document.pageCount,
              let page = document.page(at: store.currentPage) else { return }

        let pageIndex = store.currentPage
        let documentID = store.fileURL?.path ?? ""

        uiView.show(
            page: page,
            pageIndex: pageIndex,
            documentID: documentID,
            drawing: store.drawing(for: pageIndex)
        ) { drawing in
            Task { @MainActor in
                store.saveDrawing(drawing, for: pageIndex)
            }
        }
    }
}

final class PDFInkPageView: UIView, UIScrollViewDelegate, PKCanvasViewDelegate {
    private let scrollView = UIScrollView()
    private let contentView = UIView()
    private let pageImageView = UIImageView()
    private let canvasView = PKCanvasView()
    private let toolPicker = PKToolPicker()

    private var loadedPageKey: String?
    private var pageSize: CGSize = .zero
    private var didSetInitialZoom = false
    private var drawingChanged: ((PKDrawing) -> Void)?
    private var noteEditing = false

    override init(frame: CGRect) {
        super.init(frame: frame)
        backgroundColor = .systemGray6

        scrollView.delegate = self
        scrollView.backgroundColor = .systemGray6
        scrollView.showsVerticalScrollIndicator = true
        scrollView.showsHorizontalScrollIndicator = true
        scrollView.bouncesZoom = true
        scrollView.alwaysBounceVertical = false
        scrollView.alwaysBounceHorizontal = false
        scrollView.delaysContentTouches = false
        scrollView.panGestureRecognizer.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue)]
        scrollView.pinchGestureRecognizer?.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue)]

        addSubview(scrollView)
        scrollView.addSubview(contentView)

        pageImageView.contentMode = .scaleToFill
        pageImageView.backgroundColor = .white
        pageImageView.isUserInteractionEnabled = false
        contentView.addSubview(pageImageView)

        canvasView.backgroundColor = .clear
        canvasView.isOpaque = false
        canvasView.drawingPolicy = .pencilOnly
        canvasView.isScrollEnabled = false
        canvasView.delegate = self
        canvasView.drawingGestureRecognizer.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.pencil.rawValue)]
        canvasView.drawingGestureRecognizer.addTarget(self, action: #selector(pencilGestureChanged(_:)))
        contentView.addSubview(canvasView)

        toolPicker.addObserver(canvasView)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        if window != nil && !noteEditing {
            activatePencilTools()
        }
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        scrollView.frame = bounds
        updateZoomScalesIfNeeded()
        centerPage()
    }

    func setNoteEditing(_ editing: Bool) {
        guard noteEditing != editing else { return }
        noteEditing = editing

        if editing {
            canvasView.resignFirstResponder()
            toolPicker.setVisible(false, forFirstResponder: canvasView)
        } else if window != nil {
            activatePencilTools()
        }
    }

    func show(
        page: PDFPage,
        pageIndex: Int,
        documentID: String,
        drawing: PKDrawing,
        onDrawingChanged: @escaping (PKDrawing) -> Void
    ) {
        drawingChanged = onDrawingChanged
        let key = "\(documentID)#\(pageIndex)"
        guard loadedPageKey != key else { return }

        loadedPageKey = key
        didSetInitialZoom = false

        let box = page.bounds(for: .mediaBox)
        pageSize = CGSize(width: max(box.width, 1), height: max(box.height, 1))

        contentView.frame = CGRect(origin: .zero, size: pageSize)
        pageImageView.frame = contentView.bounds
        canvasView.frame = contentView.bounds
        scrollView.contentSize = pageSize

        pageImageView.image = render(page: page, bounds: box)
        canvasView.drawing = drawing

        setNeedsLayout()
        layoutIfNeeded()
        updateZoomScalesIfNeeded(force: true)

        if !noteEditing {
            activatePencilTools()
        }
    }

    @objc private func pencilGestureChanged(_ gesture: UIGestureRecognizer) {
        guard gesture.state == .began else { return }

        if noteEditing {
            noteEditing = false
            NotificationCenter.default.post(name: .lectureHelperPencilBegan, object: nil)
        }

        activatePencilTools()
    }

    private func activatePencilTools() {
        guard window != nil, !noteEditing else { return }
        if !canvasView.isFirstResponder {
            canvasView.becomeFirstResponder()
        }
        toolPicker.setVisible(true, forFirstResponder: canvasView)
    }

    private func render(page: PDFPage, bounds box: CGRect) -> UIImage {
        let size = CGSize(width: max(box.width, 1), height: max(box.height, 1))
        let format = UIGraphicsImageRendererFormat.default()
        format.opaque = true
        format.scale = max(traitCollection.displayScale, 1.0)

        return UIGraphicsImageRenderer(size: size, format: format).image { renderer in
            let ctx = renderer.cgContext
            ctx.setFillColor(UIColor.white.cgColor)
            ctx.fill(CGRect(origin: .zero, size: size))

            ctx.saveGState()
            ctx.translateBy(x: 0, y: size.height)
            ctx.scaleBy(x: 1, y: -1)
            ctx.translateBy(x: -box.origin.x, y: -box.origin.y)
            page.draw(with: .mediaBox, to: ctx)
            ctx.restoreGState()
        }
    }

    private func updateZoomScalesIfNeeded(force: Bool = false) {
        guard pageSize.width > 0, pageSize.height > 0,
              bounds.width > 0, bounds.height > 0 else { return }

        let fitWidth = bounds.width / pageSize.width
        let fitHeight = bounds.height / pageSize.height
        let fit = min(fitWidth, fitHeight)

        scrollView.minimumZoomScale = max(fit * 0.8, 0.2)
        scrollView.maximumZoomScale = max(fit * 6.0, 5.0)

        if !didSetInitialZoom || force {
            scrollView.zoomScale = fit
            didSetInitialZoom = true
            centerPage()
        }
    }

    private func centerPage() {
        let visible = scrollView.bounds.size
        let content = scrollView.contentSize
        let horizontal = max(0, (visible.width - content.width) / 2)
        let vertical = max(0, (visible.height - content.height) / 2)
        scrollView.contentInset = UIEdgeInsets(top: vertical, left: horizontal, bottom: vertical, right: horizontal)
    }

    func viewForZooming(in scrollView: UIScrollView) -> UIView? {
        contentView
    }

    func scrollViewDidZoom(_ scrollView: UIScrollView) {
        centerPage()
    }

    func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
        drawingChanged?(canvasView.drawing)
    }
}

struct ContentView: View {
    @StateObject private var store = LectureStore()
    @State private var showingImporter = false
    @State private var notesAtBottom = false
    @State private var importError: String?
    @FocusState private var noteEditorFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            topBar
            Divider()

            GeometryReader { proxy in
                if store.document == nil {
                    emptyState
                        .frame(width: proxy.size.width, height: proxy.size.height)
                } else if notesAtBottom {
                    VStack(spacing: 0) {
                        lecturePane
                            .frame(maxWidth: .infinity, maxHeight: .infinity)

                        Divider()

                        notesPane
                            .frame(height: min(max(proxy.size.height * 0.30, 200), 280))
                    }
                } else {
                    HStack(spacing: 0) {
                        lecturePane
                            .frame(maxWidth: .infinity, maxHeight: .infinity)

                        Divider()

                        notesPane
                            .frame(width: min(max(proxy.size.width * 0.25, 240), 300))
                    }
                }
            }
        }
        .fileImporter(
            isPresented: $showingImporter,
            allowedContentTypes: [.pdf],
            allowsMultipleSelection: false
        ) { result in
            do {
                guard let url = try result.get().first else { return }
                try store.importPDF(from: url)
            } catch {
                importError = error.localizedDescription
            }
        }
        .alert("PDF를 열 수 없어요", isPresented: Binding(
            get: { importError != nil },
            set: { if !$0 { importError = nil } }
        )) {
            Button("확인", role: .cancel) { importError = nil }
        } message: {
            Text(importError ?? "알 수 없는 오류")
        }
        .onReceive(NotificationCenter.default.publisher(for: .lectureHelperPencilBegan)) { _ in
            noteEditorFocused = false
        }
    }

    private var topBar: some View {
        HStack(spacing: 12) {
            Button {
                noteEditorFocused = false
                showingImporter = true
            } label: {
                Label("PDF 열기", systemImage: "doc.badge.plus")
            }
            .buttonStyle(.borderedProminent)

            Spacer()

            Button {
                noteEditorFocused = false
                store.goPrevious()
            } label: {
                Image(systemName: "chevron.left")
            }
            .buttonStyle(.bordered)
            .disabled(store.currentPage <= 0)

            Text(store.pageCount == 0 ? "– / –" : "\(store.currentPage + 1) / \(store.pageCount)")
                .font(.headline.monospacedDigit())
                .frame(minWidth: 90)

            Button {
                noteEditorFocused = false
                store.goNext()
            } label: {
                Image(systemName: "chevron.right")
            }
            .buttonStyle(.bordered)
            .disabled(store.currentPage + 1 >= store.pageCount)

            Spacer()

            Button {
                noteEditorFocused = false
                withAnimation(.easeInOut(duration: 0.18)) {
                    notesAtBottom.toggle()
                }
            } label: {
                Label(
                    notesAtBottom ? "코멘트 오른쪽" : "코멘트 하단",
                    systemImage: notesAtBottom ? "rectangle.split.2x1" : "rectangle.split.1x2"
                )
            }
            .buttonStyle(.bordered)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(.bar)
    }

    private var lecturePane: some View {
        VStack(spacing: 0) {
            PDFPencilCanvas(store: store, noteEditing: noteEditorFocused)
                .background(Color(uiColor: .systemGray6))

            Text(store.fileName)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .truncationMode(.middle)
                .frame(maxWidth: .infinity)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(Color(uiColor: .secondarySystemBackground))
        }
    }

    private var notesPane: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text("PAGE NOTE")
                        .font(.caption2.bold())
                        .foregroundStyle(.secondary)
                    Text("\(store.currentPage + 1)p.")
                        .font(.title3.bold())
                }

                Spacer()

                Button {
                    noteEditorFocused = true
                } label: {
                    Image(systemName: "keyboard")
                }
                .buttonStyle(.bordered)
                .controlSize(.mini)
                .help("노트 입력")

                Text("자동저장")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) {
                    tagButton("시험", text: "[시험] ", tint: .red)
                    tagButton("중요", text: "[중요] ", tint: .orange)
                    tagButton("교수설명", text: "[교수설명] ", tint: .blue)
                    tagButton("질문", text: "[질문] ", tint: .green)
                }
            }

            TextEditor(text: Binding(
                get: { store.noteBindingText(for: store.currentPage) },
                set: { store.setNote($0, for: store.currentPage) }
            ))
            .focused($noteEditorFocused)
            .font(.body)
            .padding(6)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .scrollContentBackground(.hidden)
            .background(Color(uiColor: .secondarySystemBackground))
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(noteEditorFocused ? Color.accentColor.opacity(0.7) : Color.secondary.opacity(0.2), lineWidth: 1)
            )

            Text(noteEditorFocused ? "⌨️ 노트 입력 중" : "✏️ Apple Pencil 필기 가능")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .padding(10)
        .background(Color(uiColor: .systemBackground))
    }

    private func tagButton(_ title: String, text: String, tint: Color) -> some View {
        Button(title) {
            store.appendTag(text, to: store.currentPage)
            noteEditorFocused = true
        }
        .buttonStyle(.bordered)
        .tint(tint)
        .controlSize(.mini)
    }

    private var emptyState: some View {
        VStack(spacing: 18) {
            Image(systemName: "pencil.and.outline")
                .font(.system(size: 54))
                .foregroundStyle(.secondary)

            Text("Lecture Helper V3")
                .font(.largeTitle.bold())

            Text("PDF를 열고 Apple Pencil로 바로 필기하세요.\n손가락은 이동·확대/축소, Pencil은 필기 전용입니다.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)

            Button {
                showingImporter = true
            } label: {
                Label("강의 PDF 선택", systemImage: "doc.badge.plus")
                    .padding(.horizontal, 6)
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(30)
    }
}
