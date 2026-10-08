import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var store: AppStore
    private var active: [VisualSkill] { store.data.skills.filter { $0.status == "active" } }
    private var headline: String {
        if !store.isConnected { return "等待连接" }
        if active.isEmpty { return "开始一项守护" }
        if active.contains(where: { $0.result == "needs_attention" }) { return "有事项需要处理" }
        if active.contains(where: { $0.result != "confirmed" }) { return "有事项尚未确认" }
        return "当前守护已确认"
    }
    private var detail: String {
        if !store.isConnected { return "连接恢复后更新守护结果" }
        if active.isEmpty { return "告诉 AI 你关心什么，确认后开始守护" }
        if active.contains(where: { $0.result == "needs_attention" }) { return "查看观察依据，处理后可请求复核" }
        if active.contains(where: { $0.result != "confirmed" }) { return "部分画面尚未确认，正在等待新证据" }
        return "已有新鲜观察依据，点击查看详情"
    }
    private var statusColor: Color {
        !store.isConnected ? Brand.muted : active.contains { $0.result == "needs_attention" } ? .orange : Brand.blue
    }
    var body: some View {
        ScrollView {
            VStack(spacing: 20) {
                VStack(spacing: -28) {
                    BrandHeader()
                    overview.padding(.horizontal, 16)
                }
                VStack(spacing: 16) {
                    HStack { Text("正在守护的 Skill").font(.title3.bold()); Spacer(); Button { store.selectedTab = 1 } label: { HStack(spacing: 4) { Text("查看全部"); Image(systemName: "chevron.right") }.font(.subheadline) } }
                    if active.isEmpty { EmptyState(title: "还没有运行中的守护", detail: "创建草案、圈选区域并确认后，任务才会开始观察。", icon: "shield") }
                    ForEach(active.prefix(3)) { skill in NavigationLink(value: AppRoute.skill(skill.id)) { SkillRow(skill: skill) }.buttonStyle(.plain) }
                    Button { store.selectedTab = 2 } label: {
                        HStack(spacing: 13) {
                            Image(systemName: "sparkles").font(.system(size: 26)).foregroundStyle(Brand.blue).frame(width: 48, height: 52).background(.white.opacity(0.6)).clipShape(RoundedRectangle(cornerRadius: 15))
                            VStack(alignment: .leading, spacing: 5) { Text("教 AI 新技能").font(.headline).foregroundStyle(Brand.dark); Text("告诉 AI 你关心的场景").font(.caption).foregroundStyle(Brand.muted) }
                            Spacer(); Image(systemName: "chevron.right").font(.subheadline).foregroundStyle(Brand.blue)
                        }.padding(15).background(LinearGradient(colors: [Brand.paleBlue, .white], startPoint: .topLeading, endPoint: .bottomTrailing)).clipShape(RoundedRectangle(cornerRadius: 18)).overlay(RoundedRectangle(cornerRadius: 18).stroke(.white, lineWidth: 1))
                    }.buttonStyle(.plain).accessibilityIdentifier("home.teach")
                }.padding(.horizontal, 16)
            }.padding(.bottom, 24)
        }.background(Brand.background).toolbar(.hidden, for: .navigationBar).refreshable { await store.refresh() }
    }
    private var overview: some View {
        VStack(alignment: .leading, spacing: 15) {
            HStack(alignment: .firstTextBaseline) {
                Text("我关心的事").font(.system(size: 18, weight: .semibold))
                Spacer(minLength: 6)
                if store.data.now > 0 {
                    Text("最近同步 " + Date(timeIntervalSince1970: store.data.now).formatted(date: .omitted, time: .shortened))
                        .font(.system(size: 10)).foregroundStyle(Brand.muted)
                }
            }
            ConnectionBanner()
            Button { if active.isEmpty && store.isConnected { store.selectedTab = 2 } else if !store.isConnected { store.path.append(.settings) } else if active.contains(where: { $0.result != "confirmed" }) { store.path.append(.alerts) } else if active.count == 1, let skill = active.first { store.path.append(.skill(skill.id)) } else { store.selectedTab = 1 } } label: {
                HStack(spacing: 15) {
                    Circle().fill(statusColor.opacity(0.10)).frame(width: 60, height: 60)
                        .overlay(Circle().fill(LinearGradient(colors: [statusColor.opacity(0.35), statusColor.opacity(0.8)], startPoint: .topLeading, endPoint: .bottomTrailing)).frame(width: 33, height: 33))
                    VStack(alignment: .leading, spacing: 7) {
                        Text(headline).font(.system(size: 19, weight: .semibold)).foregroundStyle(Brand.dark)
                        Text(detail).font(.system(size: 12)).foregroundStyle(Brand.muted).fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 0)
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(Brand.muted)
                }
            }.buttonStyle(.plain)
            HStack(spacing: 8) {
                stat("在线设备", value: store.onlineCount, icon: "video.fill", route: .cameras)
                Button { store.selectedTab = 1 } label: { statLabel("运行中 Skill", value: active.count, icon: "square.3.layers.3d") }.buttonStyle(.plain)
                stat("待处理", value: store.data.summary.openAlerts, icon: "exclamationmark.circle.fill", route: .alerts)
            }
        }.padding(16).background(.white.opacity(0.96)).clipShape(RoundedRectangle(cornerRadius: 20))
            .shadow(color: Brand.blue.opacity(0.05), radius: 12, y: 5)
    }
    private func stat(_ title: String, value: Int, icon: String, route: AppRoute) -> some View { NavigationLink(value: route) { statLabel(title, value: value, icon: icon) }.buttonStyle(.plain) }
    private func statLabel(_ title: String, value: Int, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            HStack(spacing: 7) { Image(systemName: icon).font(.system(size: 17)).foregroundStyle(Brand.blue); Text("\(value)").font(.system(size: 18, weight: .semibold)).foregroundStyle(Brand.dark); Spacer(minLength: 0); Image(systemName: "chevron.right").font(.system(size: 8)).foregroundStyle(Brand.muted) }
            Text(title).font(.system(size: 10)).foregroundStyle(Brand.muted).lineLimit(1)
        }.frame(maxWidth: .infinity).padding(.horizontal, 10).padding(.vertical, 12).background(Brand.background).clipShape(RoundedRectangle(cornerRadius: 12))
    }
}
