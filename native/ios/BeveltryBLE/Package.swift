// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BeveltryBLE",
    platforms: [.iOS(.v13), .macOS(.v12)],
    products: [.library(name: "BeveltryBLE", targets: ["BeveltryBLE"])],
    targets: [
        .target(name: "BeveltryBLE"),
        .testTarget(name: "BeveltryBLETests", dependencies: ["BeveltryBLE"])
    ]
)
