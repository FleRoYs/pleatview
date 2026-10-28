# Methods called from JavaScript in the dashboard WebView.
-keepclassmembers class com.hustlesman.pleatview.** {
    @android.webkit.JavascriptInterface <methods>;
}
