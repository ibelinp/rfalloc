// swift-tools-version:5.9
import PackageDescription

// The C reader in c/ is the canonical implementation; this package wraps it
// rather than copying it, so there is only ever one lookup implementation.
let package = Package(
    name: "RFAlloc",
    platforms: [.macOS(.v11), .iOS(.v14)],
    products: [
        .library(name: "RFAlloc", targets: ["RFAlloc"])
    ],
    targets: [
        .target(
            name: "CRFAlloc",
            path: "c",
            exclude: ["test_rfalloc.c"],
            publicHeadersPath: "."
        ),
        .target(name: "RFAlloc", dependencies: ["CRFAlloc"], path: "swift/RFAlloc"),
        .testTarget(
            name: "RFAllocTests",
            dependencies: ["RFAlloc"],
            path: "swift/RFAllocTests",
            resources: [.copy("rfalloc.bin")]
        ),
    ]
)
