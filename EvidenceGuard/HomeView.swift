import SwiftUI

struct AgentPageBackground: View {
    var body: some View {
        LinearGradient(stops: [
            .init(color: Color(red: 0.79, green: 0.89, blue: 0.97), location: 0),
            .init(color: Brand.background, location: 0.53),
            .init(color: Color(red: 0.98, green: 0.95, blue: 0.91), location: 1)
        ], startPoint: .top, endPoint: .bottom).ignoresSafeArea()
    }
}

extension View {
    func agentPageStyle(_ title: String, largeTitle: Bool = false) -> some View {
        background { AgentPageBackground() }
            .navigationTitle(title).navigationBarTitleDisplayMode(largeTitle ? .large : .inline)
            .toolbar(.visible, for: .navigationBar)
            .toolbarBackground(.hidden, for: .navigationBar)
    }
}
