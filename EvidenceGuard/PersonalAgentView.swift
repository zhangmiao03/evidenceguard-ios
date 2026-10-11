import SwiftUI

struct PersonalAgentView: View {
    @EnvironmentObject private var store: AppStore
    @State private var preferences = PersonalPreferences()
    @State private var memory = ""
    @State private var temporary = false
    @State private var loaded = false
    var body: some View {
        Form {
            Section("主动提醒") {
                Toggle("关注新事件与待处理事项", isOn: $preferences.enabled)
                Toggle("每日守护概况", isOn: $preferences.dailySummary).disabled(!preferences.enabled)
                Stepper("每日 \(preferences.summaryHour):00", value: $preferences.summaryHour, in: 0...23).disabled(!preferences.dailySummary || !preferences.enabled)
                Stepper("免打扰开始：\(preferences.quietStart):00", value: $preferences.quietStart, in: 0...23)
                Stepper("免打扰结束：\(preferences.quietEnd):00", value: $preferences.quietEnd, in: 0...23)
                Text("使用手机当前时区：\(TimeZone.current.identifier)。提醒由云端产生，打开 App 可查看；手机后台推送尚未接入。免打扰期间不产生新提醒，起止相同则全天允许提醒。").font(.caption).foregroundStyle(Brand.muted)
                Button("保存提醒偏好") {
                    preferences.timezone = TimeZone.current.identifier
                    let values = preferences
                    Task { await store.perform { store.data.personal = try await store.client.savePreferences(values); store.toast = "提醒偏好已保存" } }
                }.disabled(!loaded || !store.isConnected || store.busy)
                if let error = store.data.personal?.lastError { Text(error).foregroundStyle(.orange) }
            }
            Section("告诉助手需要记住什么") {
                TextField("例如：回复简洁一些，先说需要我做什么", text: $memory, axis: .vertical).lineLimit(2...4)
                Toggle("仅保留 24 小时", isOn: $temporary)
                Text("当天心情等临时情况可开启 24 小时有效期。只保存你主动确认的内容，不从摄像头推断心情。当前仍是团队演示空间，请使用测试信息。").font(.caption).foregroundStyle(Brand.muted)
                Button("确认记住") {
                    let content = memory.trimmingCharacters(in: .whitespacesAndNewlines)
                    Task { await store.perform { store.data.personal = try await store.client.remember(content, temporary: temporary); memory = ""; store.toast = "已记住，可随时移除" } }
                }.disabled(memory.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || memory.count > 500 || !store.isConnected || store.busy)
            }
            Section("已确认的记忆") {
                if store.data.personal?.memories.isEmpty ?? true { Text("尚未保存记忆").foregroundStyle(Brand.muted) }
                ForEach(store.data.personal?.memories ?? []) { item in
                    VStack(alignment: .leading, spacing: 6) {
                        Text(item.content)
                        Text(item.expiresAt.map { "有效至 " + displayTime($0) } ?? "保留至你主动移除").font(.caption).foregroundStyle(Brand.muted)
                        Button("移除这条记忆", role: .destructive) { Task { await store.perform { store.data.personal = try await store.client.forget(item.id) } } }.font(.caption).disabled(store.busy)
                    }
                }
            }
            Section { NavigationLink("查看助手提醒", value: AppRoute.personalInbox) }
        }.pageStyle("助手记忆与提醒")
            .task { await store.refresh(); if let snapshot = store.data.personal { preferences = snapshot.preferences; loaded = true } }
            .onChange(of: store.data.personal?.revision) { _, _ in
                if !loaded, let snapshot = store.data.personal { preferences = snapshot.preferences; loaded = true }
            }
    }
}

struct PersonalInboxView: View {
    @EnvironmentObject private var store: AppStore
    var body: some View {
        List {
            Section { NavigationLink("提醒偏好与记忆", value: AppRoute.personalAgent) }
            if store.data.personal?.inbox.isEmpty ?? true {
                Text("暂时没有助手提醒。开启后，新的任务事件、未处理事项的后续提醒和每日概况会出现在这里。")
                    .foregroundStyle(Brand.muted)
            }
            ForEach(store.data.personal?.inbox ?? []) { notice in
                VStack(alignment: .leading, spacing: 8) {
                    HStack { Text(notice.title).font(.headline); if !notice.read { Circle().fill(Brand.blue).frame(width: 7, height: 7) } }
                    Text(notice.body).font(.subheadline)
                    Text("\(notice.kindLabel) · \(displayTime(notice.createdAt))").font(.caption).foregroundStyle(Brand.muted)
                    if let id = notice.skillId { NavigationLink("查看任务和证据", value: AppRoute.skill(id)) }
                    if !notice.read { Button("标记已读") { Task { await store.perform { store.data.personal = try await store.client.readNotice(notice.id) } } }.disabled(store.busy) }
                }.padding(.vertical, 8)
            }
        }.pageStyle("助手提醒").refreshable { await store.refresh() }
    }
}
