import Foundation

struct DeviceQRCode: Equatable {
    let serial: String
    var model: String { String(serial.prefix(5)) }
    static func parse(_ raw: String) -> Self? {
        guard raw.utf8.count <= 2048 else { return nil }
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        var candidate = text
        if let data = text.data(using: .utf8), let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] {
            guard let sn = object["sn"] as? String ?? object["deviceSn"] as? String ?? object["device_sn"] as? String else { return nil }
            candidate = sn
        } else if let url = URLComponents(string: text), url.scheme != nil {
            guard ["https", "eufy", "eufysecurity"].contains(url.scheme?.lowercased() ?? ""),
                  url.user == nil, url.password == nil,
                  let items = url.queryItems else { return nil }
            let matches = items.filter { ["sn", "deviceSn", "device_sn"].contains($0.name) }
            guard matches.count == 1, let value = matches.first?.value else { return nil }
            candidate = value
        }
        let serial = candidate.trimmingCharacters(in: .whitespacesAndNewlines).uppercased()
        // A conservative identifier parser, not the vendor's undocumented pairing protocol.
        guard serial.range(of: "^T(8171|8214)[A-Z0-9]{3,27}$", options: .regularExpression) != nil else { return nil }
        return .init(serial: serial)
    }
}

struct PendingDevice: Codable, Identifiable {
    var serial: String
    var name: String
    var addedAt: Date
    var id: String { serial }
    var model: String { String(serial.prefix(5)) }
    static func load() -> [Self] {
        guard let data = UserDefaults.standard.data(forKey: "pendingDevices") else { return [] }
        return (try? JSONDecoder().decode([Self].self, from: data)) ?? []
    }
    static func save(_ devices: [Self]) {
        if let data = try? JSONEncoder().encode(devices) { UserDefaults.standard.set(data, forKey: "pendingDevices") }
    }
}
