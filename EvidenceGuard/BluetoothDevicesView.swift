import SwiftUI
import CoreBluetooth
import Combine

enum DeviceKind: String, CaseIterable, Codable {
    case mower = "除草机", camera = "摄像头", doorbell = "门铃摄像头", hub = "平板中枢", other = "其他设备"
    var icon: String {
        switch self {
        case .mower: "leaf.fill"
        case .camera: "video.fill"
        case .doorbell: "door.left.hand.closed"
        case .hub: "ipad"
        case .other: "sensor.tag.radiowaves.forward.fill"
        }
    }
}
struct SavedBluetoothDevice: Codable, Identifiable {
    var id: UUID; var name: String; var kind: DeviceKind
}

/// Only connects to an explicitly selected peripheral. No vendor command writes.
@MainActor final class BluetoothDevices: NSObject, ObservableObject, @preconcurrency CBCentralManagerDelegate, @preconcurrency CBPeripheralDelegate {
    @Published private(set) var saved: [SavedBluetoothDevice] = []
    @Published private(set) var nearby: [CBPeripheral] = []
    @Published private(set) var scanning = false
    @Published private(set) var message = "搜索附近的蓝牙设备，选择要连接的安克产品。"
    @Published private(set) var states: [UUID: String] = [:]
    @Published private(set) var batteries: [UUID: Int] = [:]
    private var central: CBCentralManager?
    private var peripherals: [UUID: CBPeripheral] = [:]
    private var pending: [UUID: SavedBluetoothDevice] = [:]
    private var deadlines: [UUID: Task<Void, Never>] = [:]
    private var scanTimer: Task<Void, Never>?
    private var scanRequested = false
    private var active = false
    private var disconnected = Set<UUID>()
    override init() {
        super.init()
        if let data = UserDefaults.standard.data(forKey: "ankerBluetoothDevices"),
           let values = try? JSONDecoder().decode([SavedBluetoothDevice].self, from: data) { saved = values }
    }
    private func persist() { UserDefaults.standard.set(try? JSONEncoder().encode(saved), forKey: "ankerBluetoothDevices") }
    func setActive(_ value: Bool) {
        active = value
        if !value { stopScan(); return }
        if !saved.isEmpty { ensureCentral(); restoreConnections() }
    }
    private func ensureCentral() {
        if central == nil { central = CBCentralManager(delegate: self, queue: .main, options: [CBCentralManagerOptionShowPowerAlertKey: true]) }
    }
    func scan() {
        active = true; scanRequested = true; ensureCentral()
        if central?.state == .poweredOn { beginScan() }
    }
    private func beginScan() {
        guard active, let central, central.state == .poweredOn else { return }
        nearby = []; scanning = true; scanRequested = false
        message = "正在搜索，请让设备进入蓝牙配对模式并靠近手机。"
        central.scanForPeripherals(withServices: nil, options: [CBCentralManagerScanOptionAllowDuplicatesKey: false])
        scanTimer?.cancel()
        scanTimer = Task { [weak self] in
            do { try await Task.sleep(for: .seconds(15)) } catch { return }
            self?.stopScan()
            self?.message = self?.nearby.isEmpty == true ? "未发现附近设备。请确认蓝牙与配对模式已开启，再搜索。" : "搜索完成，请选择你要连接的设备。"
        }
    }
    func stopScan() { if central?.state == .poweredOn { central?.stopScan() }; scanning = false; scanRequested = false; scanTimer?.cancel(); scanTimer = nil }
    func connect(_ peripheral: CBPeripheral, kind: DeviceKind, name: String) {
        guard central?.state == .poweredOn else { message = "请先打开手机蓝牙。"; return }
        disconnected.remove(peripheral.identifier)
        pending[peripheral.identifier] = SavedBluetoothDevice(id: peripheral.identifier, name: name.isEmpty ? (peripheral.name ?? "蓝牙设备") : name, kind: kind)
        startConnection(peripheral)
    }
    private func startConnection(_ peripheral: CBPeripheral) {
        guard let central, central.state == .poweredOn else { return }
        let id = peripheral.identifier
        peripherals[id] = peripheral; peripheral.delegate = self
        if peripheral.state == .connected { centralManager(central, didConnect: peripheral); return }
        guard peripheral.state != .connecting else { return }
        states[id] = "正在连接…"; central.connect(peripheral)
        deadlines[id]?.cancel()
        deadlines[id] = Task { [weak self, weak peripheral] in
            do { try await Task.sleep(for: .seconds(15)) } catch { return }
            guard let self, let peripheral, peripheral.state != .connected else { return }
            self.states[id] = "连接超时，请重试"; self.pending.removeValue(forKey: id)
            self.central?.cancelPeripheralConnection(peripheral)
        }
    }
    func reconnect(_ device: SavedBluetoothDevice) {
        disconnected.remove(device.id); ensureCentral()
        if let peripheral = central?.retrievePeripherals(withIdentifiers: [device.id]).first { startConnection(peripheral) }
    }
    func disconnect(_ id: UUID) {
        disconnected.insert(id); deadlines[id]?.cancel(); deadlines[id] = nil; pending[id] = nil
        if let peripheral = peripherals[id] { central?.cancelPeripheralConnection(peripheral) }
        states[id] = "已断开"
    }
    func forget(_ id: UUID) { disconnect(id); saved.removeAll { $0.id == id }; batteries[id] = nil; persist() }
    private func restoreConnections() {
        guard active, central?.state == .poweredOn else { return }
        for device in saved where !disconnected.contains(device.id) {
            if let peripheral = central?.retrievePeripherals(withIdentifiers: [device.id]).first { startConnection(peripheral) }
        }
    }
    func centralManagerDidUpdateState(_ central: CBCentralManager) {
        switch central.state {
        case .poweredOn:
            message = "蓝牙已开启，可搜索附近设备。"
            restoreConnections(); if scanRequested { beginScan() }
        case .poweredOff: message = "手机蓝牙已关闭，请在系统设置中开启。"
        case .unauthorized: message = "尚未允许蓝牙访问，请在设置中允许此 App 使用蓝牙。"
        case .unsupported: message = "此设备不支持蓝牙连接。"
        case .resetting: message = "蓝牙正在恢复，请稍候。"
        default: message = "正在确认蓝牙状态…"
        }
        if central.state != .poweredOn {
            scanning = false; scanTimer?.cancel()
            for task in deadlines.values { task.cancel() }; deadlines = [:]
            for id in pending.keys { states[id] = "连接不可用" }; pending = [:]
            for device in saved { states[device.id] = "连接不可用" }
        }
    }
    func centralManager(_ central: CBCentralManager, didDiscover peripheral: CBPeripheral, advertisementData: [String: Any], rssi RSSI: NSNumber) {
        guard !nearby.contains(where: { $0.identifier == peripheral.identifier }),
              advertisementData[CBAdvertisementDataIsConnectable] as? Bool != false else { return }
        peripherals[peripheral.identifier] = peripheral
        nearby.append(peripheral)
    }
    func centralManager(_ central: CBCentralManager, didConnect peripheral: CBPeripheral) {
        let id = peripheral.identifier
        deadlines[id]?.cancel(); deadlines[id] = nil; states[id] = "蓝牙已连接"
        if let value = pending.removeValue(forKey: id), !saved.contains(where: { $0.id == id }) { saved.append(value); persist() }
        peripheral.delegate = self
        peripheral.discoverServices([CBUUID(string: "180F")])
    }
    func centralManager(_ central: CBCentralManager, didFailToConnect peripheral: CBPeripheral, error: Error?) {
        deadlines[peripheral.identifier]?.cancel(); deadlines[peripheral.identifier] = nil
        pending[peripheral.identifier] = nil; states[peripheral.identifier] = "未能连接，请重试"
    }
    func centralManager(_ central: CBCentralManager, didDisconnectPeripheral peripheral: CBPeripheral, error: Error?) {
        states[peripheral.identifier] = "蓝牙已断开"; batteries[peripheral.identifier] = nil
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverServices error: Error?) {
        guard error == nil else { return }
        for service in peripheral.services ?? [] where service.uuid == CBUUID(string: "180F") { peripheral.discoverCharacteristics([CBUUID(string: "2A19")], for: service) }
    }
    func peripheral(_ peripheral: CBPeripheral, didDiscoverCharacteristicsFor service: CBService, error: Error?) {
        guard error == nil else { return }
        for item in service.characteristics ?? [] where item.uuid == CBUUID(string: "2A19") && item.properties.contains(.read) { peripheral.readValue(for: item) }
    }
    func peripheral(_ peripheral: CBPeripheral, didUpdateValueFor characteristic: CBCharacteristic, error: Error?) {
        if error == nil, characteristic.uuid == CBUUID(string: "2A19"), let value = characteristic.value?.first, value <= 100 { batteries[peripheral.identifier] = Int(value) }
    }
}

struct DevicesHomeView: View {
    @EnvironmentObject private var store: AppStore
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var bluetooth = BluetoothDevices()
    @State private var selected: CBPeripheral?
    @State private var kind: DeviceKind = .other
    @State private var name = ""
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Text("连接身边的安克设备").font(.title2.bold())
                Text("除草机、摄像头、门铃、平板中枢等设备，在这里管理蓝牙连接。").foregroundStyle(Brand.muted)
                HStack { ForEach(DeviceKind.allCases.filter { $0 != .other }, id: \.self) { kind in VStack(spacing: 8) { Image(systemName: kind.icon).font(.title2); Text(kind.rawValue).font(.caption) }.frame(maxWidth: .infinity) } }.foregroundStyle(Brand.blue)
                Text("我的蓝牙设备").font(.headline)
                if bluetooth.saved.isEmpty { Text("还没有连接蓝牙设备。搜索后，选择你的设备并确认连接。").foregroundStyle(Brand.muted) }
                ForEach(bluetooth.saved) { device in
                    VStack(alignment: .leading, spacing: 10) {
                        Label(device.name, systemImage: device.kind.icon).font(.headline)
                        Text(device.kind.rawValue + " · " + (bluetooth.states[device.id] ?? "等待连接")).font(.subheadline)
                        if let battery = bluetooth.batteries[device.id] { Label("电量 \(battery)%", systemImage: "battery.100percent").font(.caption) }
                        Text("蓝牙连接用于设备接入；此产品的专用控制能力尚未接入。").font(.caption).foregroundStyle(Brand.muted)
                        HStack {
                            Button("重新连接") { bluetooth.reconnect(device) }
                            Button("断开") { bluetooth.disconnect(device.id) }
                            Spacer()
                            Menu { Button("移除设备", role: .destructive) { bluetooth.forget(device.id) } } label: { Image(systemName: "ellipsis") }
                        }.font(.subheadline)
                    }.padding(18).frame(maxWidth: .infinity, alignment: .leading).background(.white.opacity(0.9)).clipShape(RoundedRectangle(cornerRadius: 20))
                }
                HStack {
                    Text("附近的设备").font(.headline); Spacer()
                    Button(bluetooth.scanning ? "停止搜索" : "搜索设备") { if bluetooth.scanning { bluetooth.stopScan() } else { bluetooth.scan() } }
                        .accessibilityIdentifier("devices.scan")
                }
                if bluetooth.scanning { ProgressView() }
                Text(bluetooth.message).font(.subheadline).foregroundStyle(Brand.muted).accessibilityIdentifier("devices.bluetoothStatus")
                ForEach(bluetooth.nearby.filter { p in !bluetooth.saved.contains(where: { $0.id == p.identifier }) }, id: \.identifier) { peripheral in
                    Button { name = peripheral.name ?? "蓝牙设备"; kind = .other; selected = peripheral } label: {
                        HStack { Label(peripheral.name ?? "未命名蓝牙设备", systemImage: "sensor.tag.radiowaves.forward"); Spacer(); Text(bluetooth.states[peripheral.identifier] ?? "连接").font(.caption) }
                            .padding(16).background(.white.opacity(0.85)).clipShape(RoundedRectangle(cornerRadius: 16))
                    }.disabled(bluetooth.states[peripheral.identifier] == "正在连接…")
                }
                Text("附近列表来自实际蓝牙广播，名称不能保证品牌。请只选择你认识的设备；部分产品需通过官方 App 配网。").font(.caption).foregroundStyle(Brand.muted)
                if !store.officialSDK.devices.isEmpty {
                    Text("账号连接的摄像头").font(.headline)
                    ForEach(store.officialSDK.devices.filter(\.isCompetitionCamera)) { device in
                        Button {
                            store.selectedCameraID = IOSToolExecutor.deviceID(device.sn)
                            store.selectedTab = .cameraSkills
                            Task { await store.officialSDK.selectCamera(device, client: store.client) }
                        } label: {
                            VStack(alignment: .leading, spacing: 6) { Text(device.name); Text("官方账号连接 · 非蓝牙连接").font(.caption).foregroundStyle(Brand.muted) }
                        }
                    }
                }
            }.padding(20)
        }.agentPageStyle("设备", largeTitle: true)
            .task { bluetooth.setActive(scenePhase == .active) }
            .onChange(of: scenePhase) { _, phase in bluetooth.setActive(phase == .active) }
            .sheet(isPresented: Binding(get: { selected != nil }, set: { if !$0 { selected = nil } })) {
                NavigationStack {
                    Form {
                        Text("确认这是你的设备后再连接。")
                        TextField("设备名称", text: $name)
                        Picker("产品类型", selection: $kind) { ForEach(DeviceKind.allCases, id: \.self) { Text($0.rawValue).tag($0) } }
                        Button("连接这台设备") { if let selected { bluetooth.connect(selected, kind: kind, name: name) }; selected = nil }
                    }.navigationTitle("连接蓝牙设备").toolbar { ToolbarItem(placement: .cancellationAction) { Button("取消") { selected = nil } } }
                }.presentationDetents([.medium])
            }
    }
}
