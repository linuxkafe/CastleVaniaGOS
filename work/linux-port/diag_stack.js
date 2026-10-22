// diag_stack.js — print main thread stack trace of the game process
console.log("=== diag_stack START ===");
Java.perform(function () {
    // Find the main thread and print its stack
    var Thread = Java.use("java.lang.Thread");
    var tg = Java.use("java.lang.Thread").currentThread().getThreadGroup();
    var count = tg.activeCount();
    var tarr = Java.array("java.lang.Thread", new Array(count));
    tg.enumerate(tarr);
    console.log("thread count: " + count);
    console.log("thread count: " + tarr.length);
    for (var i = 0; i < tarr.length; i++) {
        var t = tarr[i];
        if (!t) continue;
        var name = t.getName();
        if (name === "main" || name === "UnityMain" || name.indexOf("Unity") >= 0) {
            console.log("=== THREAD: " + name + " (id=" + t.getId() + ") ===");
            var stack = t.getStackTrace();
            for (var j = 0; j < stack.length; j++) {
                console.log("  at " + stack[j].toString());
            }
        }
    }
    console.log("=== diag_stack END ===");
});