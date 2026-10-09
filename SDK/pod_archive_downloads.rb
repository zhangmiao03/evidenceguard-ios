# Optional transport fallback for the public dependencies pinned in Podfile.
# Podspecs, versions and checksums remain those resolved from CocoaPods trunk.
# Fetch the same upstream tags over HTTPS; never use an unofficial mirror.
require 'cocoapods-downloader'
require 'json'
require 'digest'

class EvidenceGuardArchiveHTTP < Pod::Downloader::Http
  private

  def download_file(full_filename)
    curl! ['-f', '-L', '-sS', '--http1.1', '--connect-timeout', '15', '--max-time', '180',
           '--retry', '1', '-o', full_filename, url, '--create-dirs']
  end
end

module EvidenceGuardPodArchives
  SOURCES = {
    ['https://github.com/aws-amplify/aws-sdk-ios.git', '2.41.0'] =>
      'https://codeload.github.com/aws-amplify/aws-sdk-ios/tar.gz/refs/tags/2.41.0',
    ['https://github.com/sqlcipher/sqlcipher.git', 'v4.5.4'] =>
      'https://codeload.github.com/sqlcipher/sqlcipher/tar.gz/refs/tags/v4.5.4',
    ['https://github.com/ZipArchive/ZipArchive.git', '2.4.3'] =>
      'https://codeload.github.com/ZipArchive/ZipArchive/tar.gz/refs/tags/2.4.3'
  }.freeze
  CACHES = {
    'https://github.com/aws-amplify/aws-sdk-ios.git' => ['aws-sdk-ios-2.41.0', '1b6c1a8658ae6f4dd1e194c6373faaf109718eb8'],
    'https://github.com/sqlcipher/sqlcipher.git' => ['sqlcipher-v4.5.4', 'c7f9a1c348fde215ac18ce2b78a62ce8111a3743'],
    'https://github.com/ZipArchive/ZipArchive.git' => ['ZipArchive-2.4.3', '38e0ce0598e06b034271f296a8e15b149c91aa19']
  }.freeze

  def for_target(target_path, source_options)
    options = source_options.transform_keys(&:to_sym)
    archive = SOURCES[[options[:git], options[:tag]]]
    if archive && (options.keys - [:git, :tag]).empty?
      if cache_details = CACHES[options[:git]]
        basename, commit = cache_details
        cached = File.join(__dir__, '.tools/pod-archives', basename + '.tgz')
        manifest = cached.sub(/\.tgz$/, '.json')
        if File.file?(cached) && File.file?(manifest)
          metadata = JSON.parse(File.read(manifest))
          expected = metadata.fetch('sha256')
          unless metadata['commit'] == commit && Digest::SHA256.file(cached).hexdigest == expected
            raise Pod::Downloader::DownloaderError, 'Pod archive integrity check failed'
          end
          return EvidenceGuardArchiveHTTP.new(target_path, 'file://' + cached, :type => :tgz, :sha256 => expected)
        end
      end
      EvidenceGuardArchiveHTTP.new(target_path, archive, :type => :tgz)
    else
      super
    end
  end
end

Pod::Downloader.singleton_class.prepend(EvidenceGuardPodArchives)
