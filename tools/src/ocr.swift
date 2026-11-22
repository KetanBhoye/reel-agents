import Vision; import AppKit
for p in CommandLine.arguments.dropFirst() {
  guard let img = NSImage(contentsOfFile: p), let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else { continue }
  let r = VNRecognizeTextRequest(); r.recognitionLevel = .accurate; r.usesLanguageCorrection = true
  try? VNImageRequestHandler(cgImage: cg).perform([r])
  let lines = (r.results ?? []).sorted { $0.boundingBox.midY > $1.boundingBox.midY }.compactMap { o -> String? in
    guard let t = o.topCandidates(1).first, t.confidence > 0.4 else { return nil }
    return String(format: "[y%.2f h%.3f] ", 1 - o.boundingBox.midY, o.boundingBox.height) + t.string }
  print("## \((p as NSString).lastPathComponent)"); lines.forEach { print($0) }
}
