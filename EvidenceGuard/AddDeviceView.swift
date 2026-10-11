import SwiftUI
import AVFoundation

struct AddDeviceView: View {
    @EnvironmentObject private var store: AppStore
    @State private var scanning = false
    @State private var manual = ""
    @State private var result: DeviceQRCode?
    @State private var name = ""
    @State private var feedback: String?
    @State private var pending = PendingDevice.load()
    var body: some View {
        List {
            Section {
                Label("扫描设备上的二维码", systemImage: "qrcode.viewfinder").font(.headline)
                Text("识别设备 → 确认位置 → 验证官方绑定 → 测试画面").font(.subheadline).foregroundStyle(Brand.muted)
                Button("开始扫描") { scanning = true }.accessibilityIdentifier("devices.scan")
                DisclosureGroup("手动输入设备序列号") {
                    TextField("T8171… / T8214…", text: $manual).textInputAutocapitalization(.characters).autocorrectionDisabled()
                    Button("识别序列号") { accept(manual) }.disabled(manual.isEmpty)
                }
            }
            if let result {
                Section("确认设备") {
                    LabeledContent("型号", value: result.model)
                    LabeledContent("序列号", value: result.serial)
                    TextField("设备名称与位置", text: $name)
                    Button("保存待连接设备") {
                        pending.removeAll { $0.serial == result.serial }
                        pending.append(.init(serial: result.serial, name: String(name.prefix(40)), addedAt: Date()))
                        PendingDevice.save(pending)
                        self.result = nil
                        feedback = "设备已保存，等待官方绑定核验。尚未开始接收画面或执行任务。"
                    }.disabled(name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                }
            }
            if let feedback { Section { Text(feedback).foregroundStyle(Brand.muted).font(.subheadline) } }
            if !pending.isEmpty {
                Section("待连接设备") {
                    ForEach(pending) { device in
                        VStack(alignment: .leading, spacing: 6) {
                            Text(device.name).font(.headline)
                            Text("\(device.model) · \(device.serial)").font(.caption).foregroundStyle(Brand.muted)
                            Text("待官方绑定核验").font(.caption).foregroundStyle(.orange)
                        }.swipeActions { Button("移除", role: .destructive) { pending.removeAll { $0.id == device.id }; PendingDevice.save(pending) } }
                    }
                    NavigationLink("检查设备连接", value: AppRoute.cameras)
                }
            }
            Section("当前测试阶段") {
                Text("目前可识别并保存 T8171 / T8214 的序列号。官方配网、账号绑定协议与实物设备尚待联调；扫码不会把设备标记为已绑定。拿到摄像头后会继续完成核验和画面测试。").font(.subheadline)
            }
        }.pageStyle("添加设备")
            .sheet(isPresented: $scanning) {
                NavigationStack {
                    QRScanner { value in scanning = false; accept(value) }
                        .ignoresSafeArea(edges: .bottom)
                        .navigationTitle("扫描设备二维码").navigationBarTitleDisplayMode(.inline)
                        .toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { scanning = false } } }
                }
            }
    }
    private func accept(_ text: String) {
        guard let value = DeviceQRCode.parse(text) else {
            result = nil; feedback = "未识别到支持的设备序列号。请扫描设备标签，或手动输入 T8171 / T8214 序列号。"; return
        }
        result = value; name = value.model == "T8214" ? "门铃摄像头" : "屋檐摄像头"; feedback = nil
    }
}

private struct QRScanner: UIViewControllerRepresentable {
    var onCode: (String) -> Void
    func makeUIViewController(context: Context) -> ScannerController { ScannerController(onCode: onCode) }
    func updateUIViewController(_ uiViewController: ScannerController, context: Context) {}
    static func dismantleUIViewController(_ controller: ScannerController, coordinator: ()) { controller.stop() }
}

private final class ScannerController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    private let session = AVCaptureSession()
    private let queue = DispatchQueue(label: "com.evidenceguard.qr-camera")
    private var preview: AVCaptureVideoPreviewLayer?
    private var delivered = false
    private var visible = false
    private let onCode: (String) -> Void
    private let explanation = UILabel()
    init(onCode: @escaping (String) -> Void) { self.onCode = onCode; super.init(nibName: nil, bundle: nil) }
    required init?(coder: NSCoder) { fatalError("init(coder:) has not been implemented") }
    override func viewDidLoad() {
        super.viewDidLoad(); view.backgroundColor = .black
        explanation.textColor = .white; explanation.numberOfLines = 0; explanation.textAlignment = .center
        explanation.text = "将设备二维码放入取景画面"; explanation.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(explanation)
        NSLayoutConstraint.activate([explanation.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 24), explanation.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -24), explanation.bottomAnchor.constraint(equalTo: view.safeAreaLayoutGuide.bottomAnchor, constant: -36)])
    }
    override func viewDidAppear(_ animated: Bool) {
        super.viewDidAppear(animated); visible = true
        AVCaptureDevice.requestAccess(for: .video) { [weak self] allowed in
            DispatchQueue.main.async {
                guard let self, self.visible else { return }
                if allowed { self.configure() }
                else { self.explanation.text = "未允许相机访问。可在系统设置中开启权限，或返回手动输入序列号。" }
            }
        }
    }
    private func configure() {
        guard preview == nil else { queue.async { [session] in session.startRunning() }; return }
        guard let camera = AVCaptureDevice.default(for: .video), let input = try? AVCaptureDeviceInput(device: camera), session.canAddInput(input) else {
            explanation.text = "当前设备无法使用相机。请返回并手动输入设备序列号。"; return
        }
        session.beginConfiguration(); session.addInput(input)
        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else { session.commitConfiguration(); explanation.text = "无法启动扫描，请返回重试。"; return }
        session.addOutput(output); output.setMetadataObjectsDelegate(self, queue: .main); output.metadataObjectTypes = [.qr]
        session.commitConfiguration()
        let layer = AVCaptureVideoPreviewLayer(session: session); layer.videoGravity = .resizeAspectFill; layer.frame = view.bounds
        view.layer.insertSublayer(layer, at: 0); preview = layer
        queue.async { [session] in session.startRunning() }
    }
    override func viewDidLayoutSubviews() { super.viewDidLayoutSubviews(); preview?.frame = view.bounds }
    override func viewWillDisappear(_ animated: Bool) { super.viewWillDisappear(animated); stop() }
    func stop() { visible = false; queue.async { [session] in session.stopRunning() } }
    func metadataOutput(_ output: AVCaptureMetadataOutput, didOutput metadataObjects: [AVMetadataObject], from connection: AVCaptureConnection) {
        guard visible, !delivered, let code = metadataObjects.compactMap({ ($0 as? AVMetadataMachineReadableCodeObject)?.stringValue }).first else { return }
        delivered = true; stop(); onCode(code)
    }
}
