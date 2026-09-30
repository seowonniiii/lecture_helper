import SwiftUI
import UIKit
import PDFKit
import PencilKit

struct PDFPencilCanvas: UIViewRepresentable {
    @ObservedObject var store: LectureStore

    func makeUIView(context: Context) -> PDFInkPageView {
        PDFInkPageView()
    }

    func updateUIView(_ uiView: PDFInkPageView, context: Context) {
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

        // Fingers pan/zoom the PDF. Apple Pencil does not drive the scroll view.
        scrollView.panGestureRecognizer.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue)]
        scrollView.pinchGestureRecognizer?.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.direct.rawValue)]

        addSubview(scrollView)
        scrollView.addSubview(contentView)

        pageImageView.contentMode = .scaleToFill
        pageImageView.backgroundColor = .white
        contentView.addSubview(pageImageView)

        canvasView.backgroundColor = .clear
        canvasView.isOpaque = false
        canvasView.drawingPolicy = .pencilOnly
        canvasView.isScrollEnabled = false
        canvasView.delegate = self
        contentView.addSubview(canvasView)

        toolPicker.addObserver(canvasView)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func didMoveToWindow() {
        super.didMoveToWindow()
        guard window != nil else { return }
        toolPicker.setVisible(true, forFirstResponder: canvasView)
        canvasView.becomeFirstResponder()
    }

    override func layoutSubviews() {
        super.layoutSubviews()
        scrollView.frame = bounds
        updateZoomScalesIfNeeded()
        centerPage()
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

        toolPicker.setVisible(true, forFirstResponder: canvasView)
        canvasView.becomeFirstResponder()
    }

    private func render(page: PDFPage, bounds box: CGRect) -> UIImage {
        let size = CGSize(width: max(box.width, 1), height: max(box.height, 1))
        let format = UIGraphicsImageRendererFormat.default()
        format.opaque = true
        format.scale = UIScreen.main.scale

        return UIGraphicsImageRenderer(size: size, format: format).image { renderer in
            UIColor.white.setFill()
            renderer.fill(CGRect(origin: .zero, size: size))

            let ctx = renderer.cgContext
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
