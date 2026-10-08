import SwiftUI

enum Brand {
    static let blue = Color(red: 0.08, green: 0.43, blue: 0.98)
    static let dark = Color(red: 0.03, green: 0.07, blue: 0.16)
    static let muted = Color(red: 0.42, green: 0.50, blue: 0.62)
    static let background = Color(red: 0.965, green: 0.978, blue: 0.995)
    static let paleBlue = Color(red: 0.91, green: 0.95, blue: 1)
    static let green = Color(red: 0.05, green: 0.66, blue: 0.38)
}
extension View {
    func cardStyle(_ radius: CGFloat = 18) -> some View { background(.white).clipShape(RoundedRectangle(cornerRadius: radius)) }
    func pageStyle(_ title: String) -> some View {
        background(Brand.background).navigationTitle(title).navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
    }
}
struct BrandHeader: View {
    @EnvironmentObject var store: AppStore
    var body: some View {
        ZStack(alignment: .topLeading) {
            GeometryReader { geometry in
                Image("HomeBackdrop").resizable().scaledToFill()
                    .frame(width: geometry.size.width, height: geometry.size.height, alignment: .bottom).clipped()
            }
            LinearGradient(stops: [.init(color: .white.opacity(0.92), location: 0), .init(color: .white.opacity(0.68), location: 0.30), .init(color: .white.opacity(0.03), location: 0.70), .init(color: Brand.background.opacity(0.25), location: 1)], startPoint: .top, endPoint: .bottom)
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top, spacing: 8) {
                    VStack(alignment: .leading, spacing: 5) {
                        Text("EvidenceGuard").font(.system(size: 27, weight: .bold)).tracking(-0.7).foregroundStyle(Brand.dark)
                        Text("用 AI 守护你在乎的每一刻").font(.system(size: 14)).foregroundStyle(Brand.muted)
                    }
                    Spacer(minLength: 0)
                    Button { store.path.append(.alerts) } label: {
                        Image(systemName: store.data.summary.openAlerts > 0 ? "bell.badge" : "bell")
                            .font(.system(size: 21)).foregroundStyle(Brand.dark).frame(width: 44, height: 44)
                    }.accessibilityLabel("查看需要关注的事项").accessibilityIdentifier("home.notifications")
                }
                HStack {
                    Spacer()
                    VStack(alignment: .leading, spacing: 7) {
                        Text("更安心的\n生活，从看见开始").font(.system(size: 13, weight: .medium, design: .serif)).italic().lineSpacing(4).foregroundStyle(Brand.muted)
                        Capsule().fill(Brand.blue).frame(width: 68, height: 2)
                    }.rotationEffect(.degrees(-9)).padding(.top, 14).padding(.trailing, 4)
                }
            }.padding(.horizontal, 22).padding(.top, 13)
        }.frame(height: 220).accessibilityElement(children: .contain)
    }
}
struct ConnectionBanner: View {
    @EnvironmentObject var store: AppStore
    var body: some View {
        if !store.isConnected {
            Button { store.path.append(.settings) } label: {
                Label(store.lastError ?? "正在连接服务…", systemImage: "wifi.exclamationmark").font(.caption).frame(maxWidth: .infinity, alignment: .leading).padding(12).foregroundStyle(.orange).background(.orange.opacity(0.08)).clipShape(RoundedRectangle(cornerRadius: 12))
            }.buttonStyle(.plain)
        }
    }
}
struct StatusBadge: View {
    let text: String
    var value = "unknown"
    var color: Color { value == "confirmed" || value == "active" ? Brand.green : value == "needs_attention" ? .orange : Brand.muted }
    var body: some View { Label(text, systemImage: value == "needs_attention" ? "exclamationmark.circle.fill" : value == "confirmed" ? "checkmark.circle.fill" : "circle.dotted").font(.caption.weight(.semibold)).foregroundStyle(color).padding(.vertical, 6).padding(.horizontal, 9).background(color.opacity(0.08)).clipShape(Capsule()) }
}
struct SkillRow: View {
    @EnvironmentObject var store: AppStore
    let skill: VisualSkill
    var compact = false
    var body: some View {
        HStack(spacing: 12) {
            Image(skill.asset).resizable().scaledToFill().frame(width: 70, height: 76).clipShape(RoundedRectangle(cornerRadius: 12))
            VStack(alignment: .leading, spacing: 5) {
                Text(skill.name).font(.headline).foregroundStyle(Brand.dark)
                Text(skill.status == "draft" ? skill.prompt : skill.resultReason).font(.caption).foregroundStyle(Brand.muted).lineLimit(2)
                StatusBadge(text: store.isConnected ? skill.resultLabel : "等待连接", value: store.isConnected ? skill.result : "unknown")
            }
            Spacer(minLength: 0)
            Image(systemName: "chevron.right").font(.caption).foregroundStyle(Brand.muted)
        }.padding(12).cardStyle()
    }
}
struct EmptyState: View {
    var title: String; var detail: String; var icon = "tray"
    var body: some View { VStack(spacing: 12) { Image(systemName: icon).font(.largeTitle).foregroundStyle(Brand.blue); Text(title).font(.headline); Text(detail).font(.subheadline).foregroundStyle(Brand.muted).multilineTextAlignment(.center) }.frame(maxWidth: .infinity).padding(28).cardStyle() }
}
struct CameraFrame: View {
    @EnvironmentObject var store: AppStore
    var camera: CameraDevice?
    var showLabel = true
    var body: some View {
        Color.black.opacity(0.04).aspectRatio(1.6, contentMode: .fit)
            .overlay {
                if let camera, camera.fresh, store.isConnected, let url = store.client.absoluteURL(camera.lastFrameUrl) {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image): image.resizable().scaledToFit()
                        case .failure: Label("画面读取失败", systemImage: "video.slash").foregroundStyle(Brand.muted)
                        default: ProgressView()
                        }
                    }
                } else { Label("暂无新鲜画面", systemImage: "video.slash").foregroundStyle(Brand.muted) }
            }
            .overlay(alignment: .topLeading) {
                if showLabel { Text(camera.map { "\($0.name) · \($0.adapter.contains("fixture") ? "模拟画面" : $0.connectionLabel)" } ?? "未选择摄像头").font(.caption2).foregroundStyle(.white).padding(7).background(.black.opacity(0.55)).clipShape(Capsule()).padding(8) }
            }.clipShape(RoundedRectangle(cornerRadius: 16))
    }
}
struct PrimaryAction: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View { configuration.label.font(.headline).frame(maxWidth: .infinity).padding(.vertical, 15).foregroundStyle(.white).background(Brand.blue.opacity(configuration.isPressed ? 0.7 : 1)).clipShape(RoundedRectangle(cornerRadius: 14)) }
}
