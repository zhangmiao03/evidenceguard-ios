source 'https://cdn.cocoapods.org'
platform :ios, '17.0'
project 'EvidenceGuard.xcodeproj'

# Only the device scheme links the organizer's arm64-only SDK.
# The EvidenceGuard simulator scheme has no Kotlin/CocoaPods dependency.
target 'EvidenceGuardSDK' do
  use_frameworks!
  pod 'SampleCore', :path => 'SDK/Vendor/ESIotKit-DemoApp-Common/sample-core/SampleCore.podspec'
  pod 'SSZipArchive', '2.4.3', :modular_headers => true
  pod 'SQLCipher', '4.5.4'
  pod 'AWSCore', '2.41.0'
  pod 'AWSIoT', '2.41.0'
end

post_install do |installer|
  installer.pods_project.targets.each do |target|
    target.build_configurations.each do |configuration|
      configuration.build_settings['IPHONEOS_DEPLOYMENT_TARGET'] = '17.0'
    end
    next unless target.name == 'SampleCore'
    target.build_phases.each do |phase|
      next unless phase.respond_to?(:name)
      if phase.name == '[CP] Copy dSYMs'
        phase.shell_script = "echo 'No SampleCore dSYM in debug bootstrap'"
      end
      if phase.name == '[CP-User] Build SampleCore'
        phase.always_out_of_date = '1'
        # Keep GUI Xcode builds usable with the task-local JDK prepared by prepare.py.
        phase.shell_script = 'if [ -f "${PODS_ROOT}/../SDK/.tools/java.env" ]; then . "${PODS_ROOT}/../SDK/.tools/java.env"; fi' + "\n" + phase.shell_script
      end
    end
  end
end
