import SwiftUI
import Foundation
import UniformTypeIdentifiers
import UIKit
import WebKit
import PencilKit

@MainActor
final class HTMLPencilStore: ObservableObject {
    @Published var htmlURL: URL?
    @Published var readAccessURL: URL?
    @Published var fileName: String = ""
    @Published var fitRequest: Int = 0
    @Published var importError: String?

    private let fm = FileManager.default
    private var projectKey: String = "untitled"
    private(set) var currentDrawing = PKDrawing()

    func importHTML(_ pickedURL: URL) throws {
        let ext = pickedURL.pathExtension.lowercased()
        guard ext == "html" || ext == "htm" else {
            throw NSError(
                domain: "HTMLPencil",
                code: 10,
                userInfo: [NSLocalizedDescriptionKey: "HTML(.html/.htm) 파일을 선택해 주세요."]
            )
        }

        let accessed = pickedURL.startAccessingSecurityScopedResource()
        defer {
            if accessed { pickedURL.stopAccessingSecurityScopedResource() }
        }

        // Swift Playgrounds/iCloud 문서에서는 URL 자체를 WKWebView에 직접 넘기는 것보다
        // 먼저 바이트를 읽어 앱 Documents로 복사한 뒤 여는 방식이 훨씬 안정적임.
        let data = try Data(contentsOf: pickedURL)

        let imports = try importsDirectory()
        let base = safeName(pickedURL.deletingPathExtension().lastPathComponent)
        let project = imports.appendingPathComponent("Single_\(base)", isDirectory: true)

        if fm.fileExists(atPath: project.path) {
            try fm.removeItem(at: project)
        }
        try fm.createDirectory(at: project, withIntermediateDirectories: true)

        let originalName = pickedURL.lastPathComponent.isEmpty ? "index.html" : pickedURL.lastPathComponent
        let destination = project.appendingPathComponent(originalName)
        try data.write(to: destination, options: .atomic)

        projectKey = "Single_\(base)"
        currentDrawing = loadDrawing()
        readAccessURL = project
        htmlURL = destination
        fileName = originalName
        fitRequest += 1
    }

    func importFolder(_ pickedFolder: URL) throws {
        let accessed = pickedFolder.startAccessingSecurityScopedResource()
        defer {
            if accessed { pickedFolder.stopAccessingSecurityScopedResource() }
        }

        let imports = try importsDirectory()
        let folderName = safeName(pickedFolder.lastPathComponent)
        let destination = imports.appendingPathComponent("Folder_\(folderName)", isDirectory: true)

        if fm.fileExists(atPath: destination.path) {
            try fm.removeItem(at: destination)
        }
        try fm.copyItem(at: pickedFolder, to: destination)

        guard let html = firstHTMLFile(in: destination) else {
            throw NSError(
                domain: "HTMLPencil",
                code: 11,
                userInfo: [NSLocalizedDescriptionKey: "선택한 폴더에서 HTML 파일을 찾지 못했어요."]
            )
        }

        projectKey = "Folder_\(folderName)"
        currentDrawing = loadDrawing()
        readAccessURL = destination
        htmlURL = html
        fileName = html.lastPathComponent
        fitRequest += 1
    }

    func saveDrawing(_ drawing: PKDrawing) {
        currentDrawing = drawing
        do {
            let url = try drawingURL()
            try drawing.dataRepresentation().write(to: url, options: .atomic)
        } catch {
            print("Drawing save error:", error)
        }
    }

    private func importsDirectory() throws -> URL {
        let docs = fm.urls(for: .documentDirectory, in: .userDomainMask)[0]
        let dir = docs.appendingPathComponent("HTMLPencilImports", isDirectory: true)
        try fm.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir
    }

    private func drawingURL() throws -> URL {
        let support = fm.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("HTMLPencilDrawings", isDirectory: true)
        try fm.createDirectory(at: support, withIntermediateDirectories: true)
        return support.appendingPathComponent("\(safeName(projectKey)).drawing")
    }

    private func loadDrawing() -> PKDrawing {
        guard let url = try? drawingURL(),
              let data = try? Data(contentsOf: url),
              let drawing = try? PKDrawing(data: data) else {
            return PKDrawing()
        }
        return drawing
    }

    private func firstHTMLFile(in folder: URL) -> URL? {
        for name in ["index.html", "index.htm", "main.html", "main.htm"] {
            let candidate = folder.appendingPathComponent(name)
            if fm.fileExists(atPath: candidate.path) {
                return candidate
            }
        }

        guard let enumerator = fm.enumerator(
            at: folder,
            includingPropertiesForKeys: [.isRegularFileKey],
            options: [.skipsHiddenFiles]
        ) else { return nil }

        for case let url as URL in enumerator {
            let ext = url.pathExtension.lowercased()
            if ext == "html" || ext == "htm" {
                return url
            }
        }
        return nil
    }

    private func safeName(_ raw: String) -> String {
        let mapped = raw.map { ch -> Character in
            if ch.isLetter || ch.isNumber || ch == "-" || ch == "_" { return ch }
            return "_"
        }
        let result = String(mapped)
        return result.isEmpty ? "untitled" : result
    }
}

enum HTMLPickerMode: String, Identifiable {
    case file
    case folder

    var id: String { rawValue }
}

struct HTMLDocumentPicker: UIViewControllerRepresentable {
    let mode: HTMLPickerMode
    let onPick: (URL) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onPick: onPick, onCancel: onCancel)
    }

    func makeUIViewController(context: Context) -> UIDocumentPickerViewController {
        let picker: UIDocumentPickerViewController

        switch mode {
        case .file:
            // .data를 함께 허용해서 iCloud/Files가 HTML의 UTI를 이상하게 보고해도 선택 가능하게 함.
            var types: [UTType] = [.html, .data]
            if let htm = UTType(filenameExtension: "htm") {
                types.append(htm)
            }
            picker = UIDocumentPickerViewController(forOpeningContentTypes: types, asCopy: true)

        case .folder:
            picker = UIDocumentPickerViewController(forOpeningContentTypes: [.folder], asCopy: false)
        }

        picker.delegate = context.coordinator
        picker.allowsMultipleSelection = false
        picker.shouldShowFileExtensions = true
        return picker
    }

    func updateUIViewController(_ uiViewController: UIDocumentPickerViewController, context: Context) {}

    final class Coordinator: NSObject, UIDocumentPickerDelegate {
        let onPick: (URL) -> Void
        let onCancel: () -> Void

        init(onPick: @escaping (URL) -> Void, onCancel: @escaping () -> Void) {
            self.onPick = onPick
            self.onCancel = onCancel
        }

        func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) {
            guard let url = urls.first else {
                onCancel()
                return
            }
            onPick(url)
        }

        func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) {
            onCancel()
        }
    }
}

struct HTMLPencilDocumentView: UIViewRepresentable {
    let htmlURL: URL
    let readAccessURL: URL
    let initialDrawing: PKDrawing
    let fitRequest: Int
    let onDrawingChanged: (PKDrawing) -> Void

    func makeUIView(context: Context) -> HTMLPencilCanvasView {
        HTMLPencilCanvasView()
    }

    func updateUIView(_ uiView: HTMLPencilCanvasView, context: Context) {
        uiView.configure(
            htmlURL: htmlURL,
            readAccessURL: readAccessURL,
            initialDrawing: initialDrawing,
            fitRequest: fitRequest,
            onDrawingChanged: onDrawingChanged
        )
    }
}

final class HTMLPencilCanvasView: UIView, UIScrollViewDelegate, WKNavigationDelegate, PKCanvasViewDelegate {
    private let scrollView = UIScrollView()
    private let contentView = UIView()
    private let webView: WKWebView
    private let canvasView = PKCanvasView()
    private let toolPicker = PKToolPicker()

    private let documentWidth: CGFloat = 1024
    private var documentHeight: CGFloat = 1400
    private var loadedKey: String?
    private var lastFitRequest: Int = -1
    private var initialZoomApplied = false
    private var drawingChanged: ((PKDrawing) -> Void)?

    override init(frame: CGRect) {
        let configuration = WKWebViewConfiguration()
        configuration.defaultWebpagePreferences.allowsContentJavaScript = true
        configuration.websiteDataStore = .default()
        webView = WKWebView(frame: .zero, configuration: configuration)

        super.init(frame: frame)
        backgroundColor = .systemGray6

        scrollView.delegate = self
        scrollView.backgroundColor = .systemGray6
        scrollView.alwaysBounceVertical = true
        scrollView.alwaysBounceHorizontal = true
        scrollView.showsVerticalScrollIndicator = true
        scrollView.showsHorizontalScrollIndicator = true
        scrollView.bouncesZoom = true
        scrollView.delaysContentTouches = false
        scrollView.canCancelContentTouches = true
        scrollView.panGestureRecognizer.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue)]
        scrollView.pinchGestureRecognizer?.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue)]
        addSubview(scrollView)

        contentView.backgroundColor = .white
        scrollView.addSubview(contentView)

        webView.navigationDelegate = self
        webView.backgroundColor = .white
        webView.isOpaque = true
        webView.isUserInteractionEnabled = true
        webView.scrollView.isScrollEnabled = false
        webView.scrollView.bounces = false
        webView.scrollView.pinchGestureRecognizer?.isEnabled = false
        contentView.addSubview(webView)

        canvasView.backgroundColor = .clear
        canvasView.isOpaque = false
        canvasView.isScrollEnabled = false
        canvasView.isUserInteractionEnabled = true
        canvasView.delaysContentTouches = false
        canvasView.drawingPolicy = .pencilOnly
        canvasView.delegate = self
        contentView.addSubview(canvasView)

        // Apple Pencil drawing gets first chance; finger pans still belong to the outer scroll view.
        scrollView.panGestureRecognizer.require(toFail: canvasView.drawingGestureRecognizer)

        toolPicker.addObserver(canvasView)
        updateContentFrames()
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    deinit {
        toolPicker.removeObserver(canvasView)
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard window != nil else { return }
        showPencilTools()
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        scrollView.frame = bounds
        updateZoomLimits()
        centerDocument()

        if !initialZoomApplied, bounds.width > 0 {
            fitToWidth()
        }
    }

    func configure(
        htmlURL: URL,
        readAccessURL: URL,
        initialDrawing: PKDrawing,
        fitRequest: Int,
        onDrawingChanged: @escaping (PKDrawing) -> Void
    ) {
        drawingChanged = onDrawingChanged
        let key = htmlURL.path

        if loadedKey != key {
            loadedKey = key
            documentHeight = 1400
            initialZoomApplied = false
            canvasView.drawing = initialDrawing
            updateContentFrames()

            // 앱 내부로 복사된 HTML이므로 이 시점에는 보안 스코프 문제가 없음.
            webView.loadFileURL(htmlURL, allowingReadAccessTo: readAccessURL)
        }

        if lastFitRequest != fitRequest {
            lastFitRequest = fitRequest
            DispatchQueue.main.async { [weak self] in
                self?.fitToWidth()
            }
        }
    }

    private func updateContentFrames() {
        let size = CGSize(width: documentWidth, height: max(documentHeight, 600))
        contentView.frame = CGRect(origin: .zero, size: size)
        webView.frame = contentView.bounds
        canvasView.frame = contentView.bounds
        scrollView.contentSize = size
        updateZoomLimits()
        centerDocument()
    }

    private func updateZoomLimits() {
        guard bounds.width > 0 else { return }
        let fit = bounds.width / documentWidth
        scrollView.minimumZoomScale = max(fit * 0.75, 0.15)
        scrollView.maximumZoomScale = max(fit * 5.0, 4.0)
    }

    private func fitToWidth() {
        guard bounds.width > 0 else { return }
        updateZoomLimits()
        let fit = bounds.width / documentWidth
        scrollView.setZoomScale(fit, animated: false)
        initialZoomApplied = true
        centerDocument()
    }

    private func centerDocument() {
        let scaledWidth = documentWidth * scrollView.zoomScale
        let scaledHeight = documentHeight * scrollView.zoomScale
        let horizontal = max(0, (scrollView.bounds.width - scaledWidth) / 2)
        let vertical = max(0, (scrollView.bounds.height - scaledHeight) / 2)

        scrollView.contentInset = UIEdgeInsets(
            top: vertical,
            left: horizontal,
            bottom: vertical,
            right: horizontal
        )
    }

    private func showPencilTools() {
        guard window != nil else { return }
        canvasView.becomeFirstResponder()
        toolPicker.setVisible(true, forFirstResponder: canvasView)
    }

    func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
        // HTML 내부 JS가 Base64 이미지 src를 채우는 파일도 있으므로 여러 번 높이를 재측정함.
        refreshDocumentHeight()
        [0.2, 0.6, 1.2, 2.0].forEach { delay in
            DispatchQueue.main.asyncAfter(deadline: .now() + delay) { [weak self] in
                self?.refreshDocumentHeight()
            }
        }
    }

    func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: Error) {
        print("HTML navigation error:", error.localizedDescription)
    }

    func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: Error) {
        print("HTML provisional navigation error:", error.localizedDescription)
    }

    private func refreshDocumentHeight() {
        let script = """
        (() => {
          const b = document.body;
          const h = document.documentElement;
          return Math.max(
            b ? b.scrollHeight : 0,
            b ? b.offsetHeight : 0,
            h ? h.clientHeight : 0,
            h ? h.scrollHeight : 0,
            h ? h.offsetHeight : 0
          );
        })();
        """

        webView.evaluateJavaScript(script) { [weak self] value, error in
            guard let self else { return }
            if let error {
                print("Height JS error:", error.localizedDescription)
                return
            }

            let measured: CGFloat
            if let number = value as? NSNumber {
                measured = CGFloat(truncating: number)
            } else if let double = value as? Double {
                measured = CGFloat(double)
            } else {
                return
            }

            let newHeight = max(measured, 600)
            if abs(newHeight - self.documentHeight) > 2 {
                self.documentHeight = newHeight
                self.updateContentFrames()
            }
        }
    }

    func viewForZooming(in scrollView: UIScrollView) -> UIView? {
        contentView
    }

    func scrollViewDidZoom(_ scrollView: UIScrollView) {
        centerDocument()
    }

    func canvasViewDrawingDidChange(_ canvasView: PKCanvasView) {
        drawingChanged?(canvasView.drawing)
    }
}

struct ContentView: View {
    @StateObject private var store = HTMLPencilStore()
    @State private var pickerMode: HTMLPickerMode?

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()

            if let htmlURL = store.htmlURL,
               let readAccessURL = store.readAccessURL {
                HTMLPencilDocumentView(
                    htmlURL: htmlURL,
                    readAccessURL: readAccessURL,
                    initialDrawing: store.currentDrawing,
                    fitRequest: store.fitRequest,
                    onDrawingChanged: { drawing in
                        store.saveDrawing(drawing)
                    }
                )
            } else {
                emptyState
            }
        }
        .sheet(item: $pickerMode) { mode in
            HTMLDocumentPicker(
                mode: mode,
                onPick: { url in
                    pickerMode = nil
                    DispatchQueue.main.async {
                        do {
                            switch mode {
                            case .file:
                                try store.importHTML(url)
                            case .folder:
                                try store.importFolder(url)
                            }
                        } catch {
                            store.importError = error.localizedDescription
                        }
                    }
                },
                onCancel: {
                    pickerMode = nil
                }
            )
            .ignoresSafeArea()
        }
        .alert("열 수 없어요", isPresented: Binding(
            get: { store.importError != nil },
            set: { if !$0 { store.importError = nil } }
        )) {
            Button("확인", role: .cancel) {
                store.importError = nil
            }
        } message: {
            Text(store.importError ?? "알 수 없는 오류")
        }
    }

    private var toolbar: some View {
        HStack(spacing: 10) {
            Button {
                pickerMode = .file
            } label: {
                Label("HTML 열기", systemImage: "doc")
            }
            .buttonStyle(.borderedProminent)

            Button {
                pickerMode = .folder
            } label: {
                Label("폴더 열기", systemImage: "folder")
            }
            .buttonStyle(.bordered)

            Spacer()

            if !store.fileName.isEmpty {
                Text(store.fileName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .truncationMode(.middle)
                    .frame(maxWidth: 260)
            }

            Button {
                store.fitRequest += 1
            } label: {
                Label("폭 맞춤", systemImage: "arrow.left.and.right")
            }
            .buttonStyle(.bordered)
            .disabled(store.htmlURL == nil)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 9)
        .background(.bar)
    }

    private var emptyState: some View {
        VStack(spacing: 18) {
            Image(systemName: "pencil.tip.crop.circle.badge.plus")
                .font(.system(size: 58))
                .foregroundStyle(.secondary)

            Text("HTML Pencil")
                .font(.largeTitle.bold())

            Text("HTML 파일을 그대로 열고 Apple Pencil로 위에 필기합니다.\n손가락은 스크롤·확대/축소·HTML 버튼/링크 조작, Pencil은 필기 전용입니다.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)

            HStack(spacing: 12) {
                Button("HTML 파일 열기") {
                    pickerMode = .file
                }
                .buttonStyle(.borderedProminent)

                Button("HTML 폴더 열기") {
                    pickerMode = .folder
                }
                .buttonStyle(.bordered)
            }

            Text("지금 올린 것처럼 이미지가 HTML 안에 포함된 단일 파일은 ‘HTML 파일 열기’만 쓰면 됩니다.")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(30)
    }
}