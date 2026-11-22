import Foundation
import Vision
import CoreImage
import AppKit

let args = CommandLine.arguments
let inDir = URL(fileURLWithPath: args[1]), outDir = URL(fileURLWithPath: args[2])
// pick the instance under this point (normalized, top-left origin)
let px = Double(args[3])!, py = Double(args[4])!
let ctx = CIContext()
let files = try FileManager.default.contentsOfDirectory(atPath: inDir.path).filter{$0.hasSuffix(".png")}.sorted()
var miss = 0
for f in files {
    let url = inDir.appendingPathComponent(f)
    guard let ci = CIImage(contentsOf: url) else { continue }
    let handler = VNImageRequestHandler(ciImage: ci)
    let req = VNGenerateForegroundInstanceMaskRequest()
    try handler.perform([req])
    guard let obs = req.results?.first else { miss += 1; continue }
    // instance label at point
    let lm = obs.instanceMask
    CVPixelBufferLockBaseAddress(lm, .readOnly)
    let w = CVPixelBufferGetWidth(lm), h = CVPixelBufferGetHeight(lm)
    let rb = CVPixelBufferGetBytesPerRow(lm)
    let base = CVPixelBufferGetBaseAddress(lm)!.assumingMemoryBound(to: UInt8.self)
    let lx = Int(px * Double(w)), ly = Int(py * Double(h))
    var label = Int(base[ly * rb + lx])
    CVPixelBufferUnlockBaseAddress(lm, .readOnly)
    var set = IndexSet()
    if label == 0 { set = obs.allInstances; miss += 1 } else { set.insert(label) }
    let mask = try obs.generateScaledMaskForImage(forInstances: set, from: handler)
    let m = CIImage(cvPixelBuffer: mask)
    let clear = CIImage(color: .clear).cropped(to: ci.extent)
    let out = ci.applyingFilter("CIBlendWithMask", parameters: [kCIInputBackgroundImageKey: clear, kCIInputMaskImageKey: m])
    let o = outDir.appendingPathComponent(f)
    try ctx.writePNGRepresentation(of: out, to: o, format: .RGBA8, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!)
}
print("done", files.count, "fallbacks", miss)
