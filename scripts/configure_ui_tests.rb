# Adds ordinary Simulator API and UI tests. It does not substitute a fake
# SampleCore or pretend to compile the proprietary arm64 SDK.
require 'xcodeproj'

root = File.expand_path('..', __dir__)
project = Xcodeproj::Project.open(File.join(root, 'EvidenceGuard.xcodeproj'))
app = project.targets.find { |t| t.name == 'EvidenceGuard' }
target = project.targets.find { |t| t.name == 'EvidenceGuardUITests' } ||
  project.new_target(:ui_test_bundle, 'EvidenceGuardUITests', :ios, '17.0')
target.add_dependency(app) unless target.dependencies.any? { |d| d.target == app }
group = project.main_group.find_subpath('CompatibilityUI', true)
group.path = 'Tests/CompatibilityUI'
file = group.files.find { |f| f.path == 'WorkspaceTests.swift' } || group.new_file('WorkspaceTests.swift')
target.source_build_phase.add_file_reference(file, true)
target.build_configurations.each do |config|
  config.build_settings.merge!(
    'PRODUCT_NAME' => '$(TARGET_NAME)',
    'PRODUCT_BUNDLE_IDENTIFIER' => 'com.anker.evidenceguard.reviewtests',
    'GENERATE_INFOPLIST_FILE' => 'YES', 'SWIFT_VERSION' => '5.0',
    'TARGETED_DEVICE_FAMILY' => '1', 'TEST_TARGET_NAME' => 'EvidenceGuard',
    'CODE_SIGNING_ALLOWED' => 'NO'
  )
end
api = project.targets.find { |t| t.name == 'EvidenceGuardAPITests' } ||
  project.new_target(:unit_test_bundle, 'EvidenceGuardAPITests', :ios, '17.0')
api.add_dependency(app) unless api.dependencies.any? { |d| d.target == app }
api_group = project.main_group.find_subpath('CompatibilityAPI', true)
api_group.path = 'Tests/CompatibilityAPI'
api_file = api_group.files.find { |f| f.path == 'APIClientTests.swift' } || api_group.new_file('APIClientTests.swift')
api.source_build_phase.add_file_reference(api_file, true)
api.build_configurations.each do |config|
  config.build_settings.merge!(
    'PRODUCT_NAME' => '$(TARGET_NAME)',
    'PRODUCT_BUNDLE_IDENTIFIER' => 'com.anker.evidenceguard.apitests',
    'GENERATE_INFOPLIST_FILE' => 'YES', 'SWIFT_VERSION' => '5.0',
    'TARGETED_DEVICE_FAMILY' => '1', 'CODE_SIGNING_ALLOWED' => 'NO',
    'TEST_HOST' => '$(BUILT_PRODUCTS_DIR)/EvidenceGuard.app/$(BUNDLE_EXECUTABLE_FOLDER_PATH)/EvidenceGuard',
    'BUNDLE_LOADER' => '$(TEST_HOST)'
  )
end
project.save
scheme = Xcodeproj::XCScheme.new
scheme.add_build_target(app)
scheme.add_test_target(target)
scheme.add_test_target(api)
scheme.set_launch_target(app)
scheme.save_as(File.join(root, 'EvidenceGuard.xcodeproj'), 'EvidenceGuardReview', true)
