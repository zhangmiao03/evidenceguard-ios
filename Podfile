source 'https://cdn.cocoapods.org'
platform :ios, '17.0'
project 'EvidenceGuard.xcodeproj'
require_relative 'SDK/pod_archive_downloads' if ENV['EG_POD_ARCHIVE_DOWNLOADS'] == '1'

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
      if phase.name == '[CP-User] Build SampleCore'
        phase.always_out_of_date = '1'
        # Keep GUI Xcode builds usable with the task-local JDK prepared by prepare.py.
        phase.shell_script = 'if [ -f "${PODS_ROOT}/../SDK/.tools/java.env" ]; then . "${PODS_ROOT}/../SDK/.tools/java.env"; fi' + "\n" + phase.shell_script
        # The organizer's KMP template can write a stale MinimumOSVersion.
        # Use the built Mach-O's actual minimum, as in the official demo.
        phase.shell_script += %q(
          FRAMEWORK_DIR="$REPO_ROOT/build/cocoapods/framework/SampleCore.framework"
          FRAMEWORK_BINARY="$FRAMEWORK_DIR/SampleCore"
          FRAMEWORK_PLIST="$FRAMEWORK_DIR/Info.plist"
          if [ -f "$FRAMEWORK_BINARY" ] && [ -f "$FRAMEWORK_PLIST" ]; then
            ACTUAL_MINOS=$(xcrun otool -l "$FRAMEWORK_BINARY" | awk '/LC_BUILD_VERSION/{f=1} f && /minos/{print $2; exit} /LC_VERSION_MIN_IPHONEOS/{f=2} f==2 && /version/{print $2; exit}')
            if [ -n "$ACTUAL_MINOS" ]; then
              /usr/libexec/PlistBuddy -c "Set :MinimumOSVersion $ACTUAL_MINOS" "$FRAMEWORK_PLIST" || exit 1
            else
              echo "error: Cannot verify SampleCore MinimumOSVersion from its binary."
              exit 1
            fi
          fi
        )
      end
    end
  end
end
