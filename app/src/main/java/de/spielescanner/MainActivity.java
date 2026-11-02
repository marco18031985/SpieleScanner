package de.spielescanner;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import com.google.mlkit.vision.barcode.common.Barcode;
import com.google.mlkit.vision.codescanner.GmsBarcodeScanner;
import com.google.mlkit.vision.codescanner.GmsBarcodeScannerOptions;
import com.google.mlkit.vision.codescanner.GmsBarcodeScanning;

import org.json.JSONArray;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {

    private static final String USER_AGENT =
            "SpieleScanner/1.0 (Android; private Spielesammlung)";

    private WebView web;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService pool = Executors.newFixedThreadPool(4);

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        web = new WebView(this);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        web.addJavascriptInterface(new Bridge(), "Android");
        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                String url = request.getUrl().toString();
                if (url.startsWith("file:///android_asset/")) return false;
                openExternal(url);
                return true;
            }
        });
        setContentView(web);
        if (savedInstanceState != null) {
            web.restoreState(savedInstanceState);
        } else {
            web.loadUrl("file:///android_asset/index.html");
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle outState) {
        super.onSaveInstanceState(outState);
        web.saveState(outState);
    }

    @Override
    protected void onDestroy() {
        pool.shutdownNow();
        web.destroy();
        super.onDestroy();
    }

    private void openExternal(String url) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (ActivityNotFoundException ignored) {
        }
    }

    /** Ruft window.<fn>(args...) im WebView auf, immer auf dem UI-Thread. */
    private void callJs(final String fn, final Object... args) {
        final JSONArray arr = new JSONArray();
        for (Object a : args) arr.put(a == null ? "" : a);
        main.post(new Runnable() {
            @Override
            public void run() {
                if (web != null) {
                    web.evaluateJavascript(
                            "window." + fn + " && window." + fn + ".apply(null," + arr.toString() + ")",
                            null);
                }
            }
        });
    }

    private static String readAll(InputStream in) throws Exception {
        if (in == null) return "";
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buf = new byte[8192];
        int n;
        while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        in.close();
        return new String(out.toByteArray(), StandardCharsets.UTF_8);
    }

    private class Bridge {

        @JavascriptInterface
        public void scan() {
            main.post(new Runnable() {
                @Override
                public void run() {
                    GmsBarcodeScannerOptions options = new GmsBarcodeScannerOptions.Builder()
                            .setBarcodeFormats(
                                    Barcode.FORMAT_EAN_13,
                                    Barcode.FORMAT_EAN_8,
                                    Barcode.FORMAT_UPC_A,
                                    Barcode.FORMAT_UPC_E)
                            .build();
                    GmsBarcodeScanner scanner = GmsBarcodeScanning.getClient(MainActivity.this, options);
                    scanner.startScan()
                            .addOnSuccessListener(barcode -> callJs("onScan", barcode.getRawValue()))
                            .addOnCanceledListener(() -> callJs("onScanCancel"))
                            .addOnFailureListener(e -> callJs("onScanError", e.getMessage()));
                }
            });
        }

        @JavascriptInterface
        public void get(final String id, final String url) {
            pool.execute(new Runnable() {
                @Override
                public void run() {
                    HttpURLConnection c = null;
                    try {
                        c = (HttpURLConnection) new URL(url).openConnection();
                        c.setConnectTimeout(12000);
                        c.setReadTimeout(15000);
                        c.setRequestProperty("User-Agent", USER_AGENT);
                        c.setRequestProperty("Accept", "application/json");
                        int code = c.getResponseCode();
                        String body = readAll(code >= 400 ? c.getErrorStream() : c.getInputStream());
                        callJs("onFetch", id, code, body);
                    } catch (Exception e) {
                        callJs("onFetch", id, 0, "");
                    } finally {
                        if (c != null) c.disconnect();
                    }
                }
            });
        }

        @JavascriptInterface
        public void openUrl(final String url) {
            main.post(new Runnable() {
                @Override
                public void run() {
                    openExternal(url);
                }
            });
        }
    }
}
