import CRFAlloc
import Foundation

/// A statutory allocation: which service class owns a band, and under whose authority.
public struct Allocation: Sendable, Hashable {
    public enum Jurisdiction: UInt8, Sendable, Hashable {
        case ituRegion1 = 0, ituRegion2 = 1, ituRegion3 = 2
        case usFederal = 3, usNonFederal = 4, unitedStates = 5, europe = 6

        public var name: String {
            String(cString: rfalloc_jurisdiction_name(rawValue))
        }
    }

    public let range: Range<UInt64>
    /// Services as printed, e.g. `"FIXED, MOBILE"`; secondary ones are marked.
    public let services: String
    public let jurisdiction: Jurisdiction
    public let isNotAllocated: Bool
}

/// A curated, human-recognisable use of a frequency — what a tooltip should lead with.
public struct Channel: Sendable, Hashable {
    public let range: Range<UInt64>
    public let name: String
    public let service: String
    public let description: String
    public let mode: String

    public var centerHz: UInt64 { range.lowerBound + (range.upperBound - range.lowerBound) / 2 }
}

public enum SpectrumDatabaseError: Error, CustomStringConvertible {
    case invalid(code: Int32)

    public var description: String {
        switch self {
        case .invalid(let code): return String(cString: rfalloc_strerror(code))
        }
    }
}

/// Reverse lookup over the compiled allocation table.
///
/// The database is entirely local and read-only: opening it costs one file read,
/// and every query afterwards is a binary search over memory the instance owns.
/// It is safe to share one instance across threads and to query it from a
/// rendering path — no allocation happens inside the C reader.
public final class SpectrumDatabase: @unchecked Sendable {
    private let storage: UnsafeMutableRawBufferPointer
    private var db = rfalloc_db()

    /// Maximum entries returned by a single query. Deep stacks of overlapping
    /// curated entries are rare; this bounds the on-stack result buffers.
    private static let resultLimit = 32

    public init(data: Data) throws {
        // Validate against the caller's bytes first and only then take
        // ownership. Allocating up front would mean unwinding the allocation on
        // the failure path -- and since every stored property is initialised by
        // that point, `deinit` also runs when the initialiser throws, so
        // releasing it here as well would free the same block twice.
        var probe = rfalloc_db()
        let status = data.withUnsafeBytes { raw in
            rfalloc_open(&probe, raw.baseAddress, raw.count)
        }
        guard status == Int32(RFALLOC_OK) else {
            throw SpectrumDatabaseError.invalid(code: status)
        }

        // The C reader borrows the bytes rather than copying them, so back it
        // with storage this object owns for its whole lifetime. A pointer into
        // a `Data` would only stay valid inside `withUnsafeBytes`.
        storage = UnsafeMutableRawBufferPointer.allocate(
            byteCount: data.count, alignment: 8
        )
        _ = data.copyBytes(to: storage.bindMemory(to: UInt8.self))
        precondition(
            rfalloc_open(&db, storage.baseAddress, storage.count) == Int32(RFALLOC_OK),
            "rfalloc rejected a buffer it had already validated"
        )
    }

    public convenience init(contentsOf url: URL) throws {
        try self.init(data: try Data(contentsOf: url, options: .mappedIfSafe))
    }

    deinit { storage.deallocate() }

    // MARK: - Queries

    /// Curated uses covering `hz`, narrowest (most specific) first.
    public func channels(at hz: UInt64) -> [Channel] {
        channels(in: hz ..< (hz + 1))
    }

    /// Allocations covering `hz`, narrowest first.
    public func allocations(at hz: UInt64) -> [Allocation] {
        allocations(in: hz ..< (hz + 1))
    }

    /// Everything curated that overlaps `range` — what a spectrum display needs
    /// to draw a band ribbon under the visible span.
    public func channels(in range: Range<UInt64>) -> [Channel] {
        var raw = [rfalloc_channel](repeating: rfalloc_channel(), count: Self.resultLimit)
        let n = raw.withUnsafeMutableBufferPointer { buf in
            rfalloc_channels_in(&db, range.lowerBound, range.upperBound,
                                buf.baseAddress, Int32(buf.count))
        }
        return raw.prefix(Int(n)).map {
            Channel(range: $0.lo_hz ..< $0.hi_hz,
                    name: String(cString: $0.name),
                    service: String(cString: $0.service),
                    description: String(cString: $0.description),
                    mode: String(cString: $0.mode))
        }
    }

    public func allocations(in range: Range<UInt64>) -> [Allocation] {
        var raw = [rfalloc_band](repeating: rfalloc_band(), count: Self.resultLimit)
        let n = raw.withUnsafeMutableBufferPointer { buf in
            rfalloc_bands_in(&db, range.lowerBound, range.upperBound,
                             buf.baseAddress, Int32(buf.count))
        }
        return raw.prefix(Int(n)).compactMap { band in
            guard let j = Allocation.Jurisdiction(rawValue: band.jurisdiction) else { return nil }
            return Allocation(range: band.lo_hz ..< band.hi_hz,
                              services: String(cString: band.services),
                              jurisdiction: j,
                              isNotAllocated: band.not_allocated != 0)
        }
    }

    /// A ready-made tooltip: the recognisable name if there is one, otherwise
    /// the US allocation, which is always present.
    public func summary(at hz: UInt64) -> String {
        if let channel = channels(at: hz).first {
            return channel.name
        }
        let us = allocations(at: hz).first {
            $0.jurisdiction == .usNonFederal || $0.jurisdiction == .usFederal
        }
        guard let us, !us.services.isEmpty else { return "No allocation on record" }
        return us.services
    }
}
