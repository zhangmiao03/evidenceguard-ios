require 'xcodeproj'

root = File.expand_path('..', __dir__)
project = Xcodeproj::Project.open(File.join(root, 'EvidenceGuard.xcodeproj'))
app = project.targets.find { |target| target.name == 'EvidenceGuard' }
group = project.main_group.find_subpath('EvidenceGuard', false)
%w[OfficialSDKConnection.swift OfficialSDKSettingsView.swift OfficialSDKInspectionView.swift LiveCameraView.swift].each do |name|
  reference = group.files.find { |file| file.path == name } || group.new_file(name)
  app.source_build_phase.add_file_reference(reference, true)
end
privacy_name = 'PrivacyInfo.xcprivacy'
privacy = group.files.find { |file| file.path == privacy_name } || group.new_file(privacy_name)
app.resources_build_phase.add_file_reference(privacy, true)

target = project.targets.find { |item| item.name == 'EvidenceGuardSDK' }
unless target
  target = project.new_target(:application, 'EvidenceGuardSDK', :ios, '17.0')
end
app.source_build_phase.files.each { |file| target.source_build_phase.add_file_reference(file.file_ref, true) }
app.resources_build_phase.files.each { |file| target.resources_build_phase.add_file_reference(file.file_ref, true) }
target.build_configurations.each do |configuration|
  original = app.build_configurations.find { |item| item.name == configuration.name }
  configuration.build_settings = original.build_settings.dup
  configuration.build_settings['SUPPORTED_PLATFORMS'] = 'iphoneos'
  configuration.build_settings['EG_APP_BUNDLE_ID'] = 'com.anker.evidenceguard.sdkdemo'
  configuration.build_settings['PRODUCT_BUNDLE_IDENTIFIER'] = '$(EG_APP_BUNDLE_ID)'
  configuration.build_settings['PRODUCT_NAME'] = 'EvidenceGuardSDK'
  conditions = original.build_settings['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] || '$(inherited)'
  configuration.build_settings['SWIFT_ACTIVE_COMPILATION_CONDITIONS'] = "#{conditions} EVIDENCEGUARD_OFFICIAL_SDK"
  configuration.build_settings['FRAMEWORK_SEARCH_PATHS'] = [
    '$(inherited)', '$(PROJECT_DIR)/SDK/Vendor/ESIotKit-DemoApp-iOS/libs/ios-frameworks'
  ]
end
sdk_group = project.main_group.find_subpath('SDK', true)
sdk_group.path = 'SDK'
path = 'Vendor/ESIotKit-DemoApp-iOS/libs/ios-frameworks/AnkerWebRTC.framework'
framework = sdk_group.files.find { |file| file.path == path } || sdk_group.new_file(path)
target.frameworks_build_phase.add_file_reference(framework, true)
embed = target.copy_files_build_phases.find { |phase| phase.name == 'Embed AnkerWebRTC' } || target.new_copy_files_build_phase('Embed AnkerWebRTC')
embed.dst_subfolder_spec = '10'
embedded = embed.add_file_reference(framework, true)
embedded.settings = { 'ATTRIBUTES' => %w[CodeSignOnCopy RemoveHeadersOnCopy] }
project.save
scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(target)
scheme.set_launch_target(target)
scheme.save_as(File.join(root, 'EvidenceGuard.xcodeproj'), 'EvidenceGuardSDK', true)
puts 'Configured EvidenceGuardSDK (iPhone only) and native setup views.'
