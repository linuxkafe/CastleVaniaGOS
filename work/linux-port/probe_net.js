// probe_net.js — log all HTTP/HTTPS requests made by the game process
console.log("=== probe_net START ===");
Java.perform(function () {
    try {
        var URL = Java.use("java.net.URL");
        URL.openConnection.overload().implementation = function () {
            var url = this.toString();
            console.log("[NET] URL.openConnection: " + url);
            return this.openConnection.call(this);
        };
        console.log("[+] Hooked URL.openConnection");
    } catch (e) { console.log("[-] URL: " + e); }

    try {
        var HUC = Java.use("java.net.HttpURLConnection");
        HUC.connect.implementation = function () {
            console.log("[NET] HttpURLConnection.connect: " + this.getURL());
            return this.connect.call(this);
        };
        console.log("[+] Hooked HttpURLConnection.connect");
    } catch (e) { console.log("[-] HUC: " + e); }

    try {
        var WebView = Java.use("android.webkit.WebView");
        console.log("[+] WebView found");
    } catch (e) {}

    console.log("=== probe_net loaded ===");
});