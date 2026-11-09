#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Exercise the real launcher against disposable files, without connecting to a guest."""
import pathlib
import subprocess
import tempfile

root = pathlib.Path(__file__).resolve().parents[1]
app = root / 'dist/stage/Remote Viewer.app'
source = (root / 'src/Launcher.swift').read_text().split('final class Delegate:', 1)[0]
harness = r'''
let fm = FileManager.default
let tests = fm.temporaryDirectory.appendingPathComponent("rv-cleanup-tests-" + UUID().uuidString)
try fm.createDirectory(at: tests, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
defer { try? fm.removeItem(at: tests) }
func fixture(_ suffix: String = "vv") throws -> URL {
    let path = tests.appendingPathComponent("rv-disposable-test-" + UUID().uuidString + "." + suffix)
    try Data("[virt-viewer]\ntype=spice\nhost=cleanup-test.invalid\n".utf8).write(to: path)
    return path
}
func prepare(_ file: URL) throws -> Session {
    let session = try Session(file: file.path)
    session.process.executableURL = URL(fileURLWithPath: "/usr/bin/true")
    session.process.arguments = []
    return session
}
func launch(_ session: Session) throws {
    var finished = false
    try session.run { finished = true }
    let deadline = Date().addingTimeInterval(5)
    while !finished && Date() < deadline {
        RunLoop.current.run(until: Date().addingTimeInterval(0.02))
    }
    precondition(finished, "Process completion timed out")
}
let opened = try fixture()
let openedSession = try prepare(opened)
let copy = openedSession.directory.appendingPathComponent("connection.vv")
let originalBytes = try Data(contentsOf: opened)
let copyBytes = try Data(contentsOf: copy)
precondition(originalBytes == copyBytes, "Copy mismatch")
try launch(openedSession)
precondition(!fm.fileExists(atPath: opened.path), "Opened .vv was not trashed")
print("PASS: opened .vv moves to Trash after process launch")

let failed = try fixture()
let failedSession = try prepare(failed)
failedSession.process.executableURL = URL(fileURLWithPath: "/nonexistent/remote-viewer-cleanup-test")
do { try failedSession.run {}; fatalError("Expected launch failure") } catch {}
precondition(fm.fileExists(atPath: failed.path), "Failed launch trashed the source")
try fm.removeItem(at: failedSession.directory)
print("PASS: failed process launch retains the source")

let changed = try fixture()
let changedSession = try prepare(changed)
try Data("new download".utf8).write(to: changed)
try launch(changedSession)
precondition(fm.fileExists(atPath: changed.path), "Changed download was trashed")
print("PASS: source replaced after copying is retained")

let other = try fixture("txt")
try launch(prepare(other))
precondition(fm.fileExists(atPath: other.path), "Non-.vv input was trashed")
print("PASS: non-.vv inputs are retained")
'''
executable = app / 'Contents/MacOS/LauncherCleanupTest'
try:
    with tempfile.TemporaryDirectory(prefix='rv-cleanup-build-') as temporary:
        swift = pathlib.Path(temporary) / 'main.swift'
        swift.write_text(source + harness)
        subprocess.run(['xcrun','swiftc',str(swift),'-o',str(executable)],check=True)
        subprocess.run([str(executable)],check=True,timeout=30)
finally:
    executable.unlink(missing_ok=True)
