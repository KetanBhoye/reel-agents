// fgmask <image> <out.png> [person]
// Writes a full-resolution grayscale mask of the image's foreground (macOS Vision).
// "person" uses accurate person segmentation instead of the generic foreground mask.
import Foundation
import Vision
import CoreImage
import AppKit

let args = CommandLine.arguments
guard args.count >= 3 else { print("usage: fgmask <image> <out.png> [person]"); exit(1) }
let url = URL(fileURLWithPath: args[1])
guard let ci = CIImage(contentsOf: url, options: [.applyOrientationProperty: true]) else { print("cannot read"); exit(1) }
let handler = VNImageRequestHandler(ciImage: ci, options: [:])
var maskBuf: CVPixelBuffer?
if args.count > 3 && args[3] == "person" {
    let r = VNGeneratePersonSegmentationRequest(); r.qualityLevel = .accurate
    r.outputPixelFormat = kCVPixelFormatType_OneComponent8
    try handler.perform([r]); maskBuf = r.results?.first?.pixelBuffer
} else {
    let r = VNGenerateForegroundInstanceMaskRequest()
    try handler.perform([r])
    if let obs = r.results?.first { maskBuf = try obs.generateScaledMaskForImage(forInstances: obs.allInstances, from: handler) }
}
guard let mb = maskBuf else { print("no mask"); exit(2) }
var m = CIImage(cvPixelBuffer: mb)
m = m.transformed(by: CGAffineTransform(scaleX: ci.extent.width / m.extent.width, y: ci.extent.height / m.extent.height))
let ctx = CIContext()
let cs = CGColorSpaceCreateDeviceGray()
try ctx.writePNGRepresentation(of: m, to: URL(fileURLWithPath: args[2]), format: .L8, colorSpace: cs)
print("ok", Int(ci.extent.width), Int(ci.extent.height))
