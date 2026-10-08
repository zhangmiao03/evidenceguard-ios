import SwiftUI
import Speech
import AVFoundation

@MainActor final class SpeechInput: ObservableObject {
    enum Phase { case idle, requesting, recording, finishing }
    @Published var phase: Phase = .idle
    @Published var transcript = ""
    @Published var error: String?
    private let engine = AVAudioEngine()
    private let recognizer = SFSpeechRecognizer(locale: Locale(identifier: "zh-CN"))
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private var tapInstalled = false
    private var held = false
    private var generation = UUID()
    private var completion: ((String) -> Void)?

    func begin(onFinished: @escaping (String) -> Void) {
        guard phase == .idle else { return }
        held = true; transcript = ""; error = nil; completion = onFinished
        phase = .requesting
        let token = UUID(); generation = token
        Task {
            let speech = await withCheckedContinuation { continuation in
                SFSpeechRecognizer.requestAuthorization { continuation.resume(returning: $0) }
            }
            let microphone = await AVAudioApplication.requestRecordPermission()
            guard generation == token else { return }
            guard speech == .authorized, microphone else {
                error = "请在系统设置中允许麦克风和语音识别，或使用键盘输入。"; phase = .idle; return
            }
            guard held else { phase = .idle; error = "权限已准备好，请重新按住说话。"; return }
            guard let recognizer, recognizer.isAvailable else { error = "语音识别暂不可用，请使用文字输入。"; phase = .idle; return }
            do {
                let session = AVAudioSession.sharedInstance()
                try session.setCategory(.record, mode: .measurement, options: .duckOthers)
                try session.setActive(true, options: .notifyOthersOnDeactivation)
                let req = SFSpeechAudioBufferRecognitionRequest()
                req.shouldReportPartialResults = true
                if recognizer.supportsOnDeviceRecognition { req.requiresOnDeviceRecognition = true }
                request = req
                let input = engine.inputNode
                let format = input.outputFormat(forBus: 0)
                guard format.sampleRate > 0, format.channelCount > 0 else { throw APIProblem(message: "没有可用麦克风，请在真机重试或输入文字。") }
                input.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in req.append(buffer) }
                tapInstalled = true
                task = recognizer.recognitionTask(with: req) { [weak self] result, err in
                    Task { @MainActor in
                        guard let self, self.generation == token else { return }
                        if let result { self.transcript = result.bestTranscription.formattedString }
                        if result?.isFinal == true || err != nil {
                            if self.transcript.isEmpty, err != nil { self.error = "未识别到语音，请重试或改用文字。" }
                            self.finish(deliver: self.phase == .finishing || result?.isFinal == true)
                        }
                    }
                }
                engine.prepare(); try engine.start(); phase = .recording
                Task { try? await Task.sleep(for: .seconds(45)); if self.generation == token, self.phase == .recording { self.end() } }
            } catch { self.error = error.localizedDescription; finish(deliver: false) }
        }
    }
    func end() {
        held = false
        guard phase == .recording else { return }
        phase = .finishing; stopAudio(); request?.endAudio()
        let token = generation
        Task { try? await Task.sleep(for: .milliseconds(1300)); if generation == token, phase == .finishing { finish(deliver: true) } }
    }
    func cancel() { held = false; finish(deliver: false) }
    private func stopAudio() {
        engine.stop()
        if tapInstalled { engine.inputNode.removeTap(onBus: 0); tapInstalled = false }
        try? AVAudioSession.sharedInstance().setActive(false, options: .notifyOthersOnDeactivation)
    }
    private func finish(deliver: Bool) {
        let text = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        let callback = completion
        generation = UUID(); stopAudio(); task?.cancel(); task = nil; request = nil; completion = nil; phase = .idle
        if deliver {
            if !text.isEmpty { callback?(text) } else { error = "没有听清内容，没有发送任何请求。请重新录音。" }
        }
    }
}

struct VoiceCaptureButton: View {
    @StateObject private var speech = SpeechInput()
    let onTranscript: (String) -> Void
    @State private var pressing = false
    var body: some View {
        VStack(spacing: 12) {
            if !speech.transcript.isEmpty { Text(speech.transcript).font(.body).frame(maxWidth: .infinity, alignment: .leading).padding(12).background(Brand.paleBlue).clipShape(RoundedRectangle(cornerRadius: 12)) }
            ZStack {
                Circle().fill(Brand.blue.opacity(0.1)).frame(width: 116, height: 116)
                Circle().fill(speech.phase == .recording ? Color.red : Brand.blue).frame(width: 88, height: 88)
                if speech.phase == .requesting || speech.phase == .finishing { ProgressView().tint(.white) }
                else { Image(systemName: speech.phase == .recording ? "waveform" : "mic.fill").font(.system(size: 30)).foregroundStyle(.white) }
            }
            .contentShape(Circle())
            .gesture(DragGesture(minimumDistance: 0).onChanged { _ in
                if !pressing { pressing = true; speech.begin(onFinished: onTranscript) }
            }.onEnded { _ in pressing = false; speech.end() })
            .accessibilityElement().accessibilityLabel("按住说话").accessibilityIdentifier("ai.record")
            .accessibilityAction(named: "开始录音") { speech.begin(onFinished: onTranscript) }
            .accessibilityAction(named: "结束录音") { speech.end() }
            Text(speech.phase == .recording ? "正在听，松开后编辑" : speech.phase == .finishing ? "正在完成转写…" : "按住说话，松开后编辑").font(.subheadline).foregroundStyle(Brand.muted)
            if speech.phase == .recording { Button("取消录音", role: .cancel) { pressing = false; speech.cancel() } }
            if let error = speech.error { Text(error).font(.caption).foregroundStyle(.orange) }
        }.onDisappear { speech.cancel() }
    }
}
