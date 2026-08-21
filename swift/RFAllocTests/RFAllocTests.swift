import XCTest
@testable import RFAlloc

final class RFAllocTests: XCTestCase {
    private func loadDatabase() throws -> SpectrumDatabase {
        let url = try XCTUnwrap(
            Bundle.module.url(forResource: "rfalloc", withExtension: "bin")
        )
        return try SpectrumDatabase(contentsOf: url)
    }

    func testResolvesWeatherRadio() throws {
        let db = try loadDatabase()
        let hits = db.channels(at: 162_550_000)
        XCTAssertEqual(hits.first?.name, "NOAA Weather Radio WX1")
        XCTAssertEqual(db.summary(at: 162_550_000), "NOAA Weather Radio WX1")
    }

    func testFallsBackToAllocationWhenNothingIsCurated() throws {
        let db = try loadDatabase()
        // 1350 MHz has no curated entry, so the statutory allocation answers.
        // The allocation layer has no gaps, so a lookup can never come back empty.
        XCTAssertTrue(db.channels(at: 1_350_000_000).isEmpty)
        XCTAssertEqual(db.summary(at: 1_350_000_000), "FIXED, MOBILE, RADIOLOCATION")
    }

    func testCarriesEuropeanChannels() throws {
        let db = try loadDatabase()
        XCTAssertEqual(db.channels(at: 446_006_250).first?.name, "PMR446 Channel 1")
        XCTAssertEqual(db.channels(at: 77_500).first?.name, "DCF77 (77.5 kHz)")
    }

    func testRegionOneDiffersFromTheAmericas() throws {
        let db = try loadDatabase()
        // Amateur is primary at 432-438 MHz in Region 1 and secondary in Region 2.
        let allocations = db.allocations(at: 433_920_000)
        let r1 = try XCTUnwrap(allocations.first { $0.jurisdiction == .ituRegion1 })
        let r2 = try XCTUnwrap(allocations.first { $0.jurisdiction == .ituRegion2 })
        XCTAssertTrue(r1.services.hasPrefix("AMATEUR"))
        XCTAssertTrue(r2.services.contains("Amateur (secondary)"))
    }

    func testNarrowestMatchRanksFirst() throws {
        let db = try loadDatabase()
        let hits = db.channels(at: 156_800_000)
        XCTAssertEqual(hits.first?.name, "Marine VHF Channel 16")
        let widths = hits.map { $0.range.upperBound - $0.range.lowerBound }
        XCTAssertEqual(widths, widths.sorted(), "results must widen monotonically")
    }

    func testHalfOpenRangesDoNotDoubleCount() throws {
        let db = try loadDatabase()
        // 148 MHz is the boundary between the amateur 2 m band and what follows;
        // a half-open range must place it in exactly one band per jurisdiction.
        let federal = db.allocations(at: 148_000_000).filter { $0.jurisdiction == .usFederal }
        XCTAssertEqual(federal.count, 1)
        XCTAssertEqual(federal.first?.range.lowerBound, 148_000_000)
    }

    func testSpanQueryCoversVisibleWaterfall() throws {
        let db = try loadDatabase()
        let visible = db.channels(in: 144_000_000 ..< 148_000_000)
        XCTAssertGreaterThanOrEqual(visible.count, 3)
        XCTAssertTrue(visible.allSatisfy { $0.range.overlaps(144_000_000 ..< 148_000_000) })
    }

    func testRejectsCorruptData() {
        XCTAssertThrowsError(try SpectrumDatabase(data: Data([0, 1, 2, 3])))
    }
}
