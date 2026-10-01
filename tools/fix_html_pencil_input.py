from pathlib import Path

p = Path('html-pencil-ipad/ContentView.swift')
s = p.read_text(encoding='utf-8')

old = '''// 손가락은 아래 HTML/스크롤로 통과시키고 Apple Pencil 터치만 받는 캔버스.\nfinal class PencilOnlyHitCanvasView: PKCanvasView {\n    override func point(inside point: CGPoint, with event: UIEvent?) -> Bool {\n        guard super.point(inside: point, with: event) else { return false }\n        guard let touches = event?.allTouches, !touches.isEmpty else { return false }\n        return touches.contains { $0.type == .pencil }\n    }\n}\n\n'''
s = s.replace(old, '')
s = s.replace('private let canvasView = PencilOnlyHitCanvasView()', 'private let canvasView = PKCanvasView()')
s = s.replace('        canvasView.drawingGestureRecognizer.allowedTouchTypes = [NSNumber(value: UITouch.TouchType.pencil.rawValue)]\n', '')

needle = '''        canvasView.isScrollEnabled = false\n        canvasView.drawingPolicy = .pencilOnly\n        canvasView.delegate = self\n        contentView.addSubview(canvasView)\n'''
replacement = '''        canvasView.isScrollEnabled = false\n        canvasView.isUserInteractionEnabled = true\n        canvasView.delaysContentTouches = false\n        canvasView.drawingPolicy = .pencilOnly\n        canvasView.delegate = self\n        contentView.addSubview(canvasView)\n\n        // Apple Pencil drawing gets first chance; finger pans still belong to the outer scroll view.\n        scrollView.panGestureRecognizer.require(toFail: canvasView.drawingGestureRecognizer)\n'''
if needle not in s:
    raise SystemExit('canvas setup block not found')
s = s.replace(needle, replacement, 1)

p.write_text(s, encoding='utf-8')
