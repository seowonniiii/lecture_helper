import SwiftUI
import UniformTypeIdentifiers

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
                            .frame(
                                height: min(
                                    max(proxy.size.height * 0.32, 220),
                                    300
                                )
                            )
                    }
                } else {
                    HStack(spacing: 0) {
                        lecturePane
                            .frame(maxWidth: .infinity, maxHeight: .infinity)

                        Divider()

                        notesPane
                            .frame(
                                width: min(
                                    max(proxy.size.width * 0.28, 260),
                                    320
                                )
                            )
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
        .onChange(of: noteEditorFocused) { _, focused in
            if focused {
                NotificationCenter.default.post(
                    name: .lectureHelperNoteEditingBegan,
                    object: nil
                )
            }
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
            PDFPencilCanvas(store: store)
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
                    .stroke(Color.secondary.opacity(0.2), lineWidth: 1)
            )
            .contentShape(Rectangle())
            .simultaneousGesture(
                TapGesture().onEnded {
                    NotificationCenter.default.post(
                        name: .lectureHelperNoteEditingBegan,
                        object: nil
                    )
                    noteEditorFocused = true
                }
            )

            Text("Apple Pencil 필기는 페이지별 자동저장")
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
