// diag_threads.js — native thread enumeration + backtrace via Frida
console.log("=== diag_threads START ===");
var threads = Process.enumerateThreads();
console.log("thread count: " + threads.length);
for (var i = 0; i < threads.length; i++) {
    var t = threads[i];
    console.log("--- thread id=" + t.id + " name=" + (t.name || "?") + " state=" + t.state + " ---");
    try {
        var bt = Thread.backtrace(t.context, Backtracer.ACCURATE);
        for (var j = 0; j < Math.min(bt.length, 16); j++) {
            var sym = DebugSymbol.fromAddress(bt[j]);
            console.log("   #" + j + " " + bt[j] + " " + (sym ? sym.name + " " + sym.moduleName : ""));
        }
    } catch (e) {
        console.log("   backtrace err: " + e);
    }
}
console.log("=== diag_threads END ===");